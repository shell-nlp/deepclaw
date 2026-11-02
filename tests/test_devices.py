"""设备归属、配对、权限撤销、任务重放和连接隔离测试。"""

import asyncio
from threading import Event
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, WebSocketDisconnect
from fastapi.testclient import TestClient
from langchain_core.messages import SystemMessage

from deepclaw.web_backend.auth.dependencies import CurrentActor, get_current_actor
from deepclaw.web_backend.devices.router import router
from deepclaw.web_backend.devices.schemas import DevicePolicyRequest, DeviceEventRequest
from deepclaw.web_backend.devices.store import DeviceStore, get_device_store
from deepclaw.middleware.device_tools import DeviceToolsMiddleware


async def paired(store, user="alice", enabled=True):
    """建立测试设备并连接，使用真实临时数据库。

    Args:
        store: 隔离存储。
        user: 设备归属用户。
        enabled: 是否开启测试授权。
    """
    code, _ = await store.pair(user)
    device_id, token = await store.claim(code, "办公电脑", "win32")
    assert await store.connect(device_id, "connection-a")
    await store.policy(device_id, "connection-a", DevicePolicyRequest(enabled=enabled, revision=1,
        capabilities=["files.read", "command.run"], roots=["D:\\工作"] ))
    return device_id, token


def test_pairing_is_single_use_and_credentials_are_hashed(tmp_path):
    """配对码只可使用一次，设备默认关闭且数据库不含原始令牌。

    Args:
        tmp_path: 隔离数据库目录。
    """
    async def run():
        """验证配对消费与默认状态。

        Args:
            无。
        """
        store = DeviceStore(f"sqlite:///{tmp_path / 'devices.db'}")
        try:
            code, _ = await store.pair("alice")
            device_id, token = await store.claim(code, "电脑", "win32")
            device = await store.device(device_id)
            assert not device.enabled
            assert device.token_hash != token
            assert await store.authenticate(token)
            with pytest.raises(ValueError):
                await store.claim(code, "另一台", "win32")
        finally:
            await store.engine.dispose()
    asyncio.run(run())


def test_tasks_enforce_owner_switch_and_idempotency(tmp_path):
    """跨用户不可执行，开关关闭后旧调用被拒绝，同调用不重建任务。

    Args:
        tmp_path: 隔离数据库目录。
    """
    async def run():
        """验证即时授权和去重。

        Args:
            无。
        """
        store = DeviceStore(f"sqlite:///{tmp_path / 'devices.db'}")
        try:
            device_id, _ = await paired(store)
            arguments = dict(device_id=device_id, user_id="alice", operation="read_file", arguments={"path": "D:\\工作\\a.txt"}, thread_id="thread", tool_call_id="call")
            with pytest.raises(ValueError):
                await store.create_task(**{**arguments, "user_id": "bob"})
            task = await store.create_task(**arguments)
            assert (await store.create_task(**arguments)).id == task.id
            await store.policy(device_id, "connection-a", DevicePolicyRequest(enabled=False, revision=2, capabilities=[], roots=[]))
            assert (await store.task(task.id)).cancel_requested
            with pytest.raises(ValueError):
                await store.create_task(**{**arguments, "tool_call_id": "new-call"})
            with pytest.raises(ValueError):
                await store.policy(device_id, "connection-a", DevicePolicyRequest(enabled=True, revision=1, capabilities=["files.read"], roots=[]))
        finally:
            await store.engine.dispose()
    asyncio.run(run())


def test_connection_lease_and_event_replay_cannot_overwrite(tmp_path):
    """旧连接和迟到事件不能覆盖新连接与终止结果。

    Args:
        tmp_path: 隔离数据库目录。
    """
    async def run():
        """竞争连接并重放输出。

        Args:
            无。
        """
        store = DeviceStore(f"sqlite:///{tmp_path / 'devices.db'}")
        try:
            device_id, token = await paired(store)
            assert not await store.connect(device_id, "connection-b")
            task = await store.create_task(device_id=device_id, user_id="alice", operation="run_command", arguments={}, thread_id="t", tool_call_id="c")
            event = DeviceEventRequest(task_id=task.id, sequence=1, status="running", output="唯一输出")
            await store.event(device_id, "connection-a", event)
            await store.event(device_id, "connection-a", event)
            assert (await store.task(task.id)).output == "唯一输出"
            await store.event(device_id, "connection-a", DeviceEventRequest(task_id=task.id, sequence=2, status="succeeded", result={"exit_code": 0}))
            await store.event(device_id, "connection-a", DeviceEventRequest(task_id=task.id, sequence=3, status="running"))
            assert (await store.task(task.id)).status == "succeeded"
            await store.disconnect(device_id, "connection-a")
            assert await store.connect(device_id, "connection-b")
            await store.disconnect(device_id, "connection-a")
            assert (await store.device(device_id)).connection_id == "connection-b"
            with pytest.raises(ValueError):
                await store.event(device_id, "connection-a", event)
            await store.revoke(device_id, "alice")
            assert await store.authenticate(token) is None
        finally:
            await store.engine.dispose()
    asyncio.run(run())


def test_device_api_ownership_and_real_websocket(tmp_path):
    """通过真实 ASGI WebSocket 验证连接、授权、凭据与管理 API。

    Args:
        tmp_path: 隔离数据库目录。
    """
    store = DeviceStore(f"sqlite:///{tmp_path / 'devices.db'}")
    disconnected = Event()
    disconnect = store.disconnect

    async def finish_disconnect(device_id, connection_id):
        """等待连接租约释放完成后再结束测试客户端。

        Args:
            device_id: 测试设备。
            connection_id: 当前连接。
        """
        await disconnect(device_id, connection_id)
        disconnected.set()

    store.disconnect = finish_disconnect
    app = FastAPI()
    app.include_router(router)
    current = {"id": "alice"}
    app.dependency_overrides[get_device_store] = lambda: store
    app.dependency_overrides[get_current_actor] = lambda: CurrentActor(is_guest=False, user_id=current["id"], email="a@example.com", role="user")
    with TestClient(app) as client:
        pairing = client.post("/api/devices/pairings").json()
        claim = client.post("/api/devices/pairings/claim", json={"code": pairing["code"], "name": "办公电脑", "platform": "win32"}).json()
        assert "token" in claim
        device_id = claim["device_id"]
        current["id"] = "bob"
        assert client.get("/api/devices").json()["items"] == []
        assert client.get(f"/api/devices/{device_id}/tasks").status_code == 404
        assert client.delete(f"/api/devices/{device_id}").status_code == 404
        current["id"] = "alice"
        with client.websocket_connect("/api/devices/connect", headers={"Authorization": "Bearer " + claim["token"]}) as ws:
            assert ws.receive_json()["type"] == "welcome"
            ws.send_json({"type": "policy", "enabled": True, "revision": 1, "capabilities": ["files.read"], "roots": ["D:\\工作"]})
            assert ws.receive_json()["type"] == "policy_ack"
            devices = client.get("/api/devices").json()["items"]
            assert devices[0]["enabled"]
            assert "token_hash" not in devices[0]
            assert client.delete(f"/api/devices/{device_id}").status_code == 204
            with pytest.raises(WebSocketDisconnect):
                ws.receive_json()
            assert disconnected.wait(3)
        assert client.get("/api/devices").json()["items"] == []
    asyncio.run(store.engine.dispose())


def test_device_middleware_hides_closed_devices_and_blocks_forged_tool(tmp_path):
    """模型仅看到自己的开启设备，关闭后直接调用旧工具也被拒绝。

    Args:
        tmp_path: 隔离数据库目录。
    """
    async def run():
        """验证模型工具列表与真实执行权限。

        Args:
            无。
        """
        store = DeviceStore(f"sqlite:///{tmp_path / 'devices.db'}")
        class Request:
            """保留真实 override 行为的最小模型请求。"""
            def __init__(self, state, tools=None, system_message=None):
                """保存请求字段。

                Args:
                    state: 可信状态。
                    tools: 工具列表。
                    system_message: 系统消息。
                """
                self.state, self.tools, self.system_message = state, tools or [], system_message or SystemMessage(content="原提示")

            def override(self, **changes):
                """创建新请求，不修改原共享对象。

                Args:
                    changes: 本次修改字段。
                """
                return Request(self.state, changes.get("tools", self.tools), changes.get("system_message", self.system_message))

        async def handler(request):
            """返回模型收到的请求以检查隔离。

            Args:
                request: 最终请求。
            """
            return request

        try:
            device_id, _ = await paired(store)
            middleware = DeviceToolsMiddleware(store)
            request = Request({"user_id": "alice", "device_id": device_id})
            result = await middleware.awrap_model_call(request, handler)
            assert {tool.name for tool in result.tools} == {"device_list_files", "device_read_file", "device_run_command"}
            assert request.tools == []
            assert not (await middleware.awrap_model_call(Request({"user_id": "bob"}), handler)).tools
            assert not (await middleware.awrap_model_call(Request({"user_id": "alice", "device_id": None}), handler)).tools
            await store.policy(device_id, "connection-a", DevicePolicyRequest(enabled=False, revision=2, capabilities=[], roots=[]))
            assert not (await middleware.awrap_model_call(request, handler)).tools
            call = SimpleNamespace(state={"user_id": "alice", "device_id": device_id}, tool_call={"id": "forged", "name": "device_read_file", "args": {"device_id": device_id, "path": "D:\\工作\\a.txt"}}, runtime=SimpleNamespace(execution_info=SimpleNamespace(thread_id="thread")))
            message = await middleware.awrap_tool_call(call, handler)
            assert message.status == "error"
            assert not await store.tasks(device_id)
        finally:
            await store.engine.dispose()
    asyncio.run(run())


@pytest.mark.parametrize("use_deferred", [False, True])
def test_real_agent_routes_dynamic_device_tool_and_returns_result(tmp_path, use_deferred):
    """验证真实 Agent 图将动态工具路由到设备队列并接收工具结果。

    Args:
        tmp_path: 隔离数据库目录。
        use_deferred: 是否启用真实延迟工具中间件。
    """
    from langchain.agents import create_agent
    from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
    from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
    from deepclaw.agents.general.state import StateSchema

    async def run():
        """组装真实图并通过临时存储模拟客户端回执。

        Args:
            无。
        """
        store = DeviceStore(f"sqlite:///{tmp_path / 'devices.db'}")
        bound_tools = []

        class Model(GenericFakeChatModel):
            """支持工具绑定的确定性测试模型。"""

            def bind_tools(self, tools, **kwargs):
                """记录模型可见工具并保留固定响应。

                Args:
                    tools: 本轮可见工具。
                    kwargs: 模型绑定参数。
                """
                bound_tools.extend(tool.name for tool in tools)
                return self

        try:
            device_id, _ = await paired(store)
            model = Model(messages=iter([
                AIMessage(content="", tool_calls=[{"id": "actual-call", "name": "device_read_file", "args": {"device_id": device_id, "path": "D:\\工作\\a.txt"}}]),
                AIMessage(content="已读取本机文件"),
            ]))
            middleware = [DeviceToolsMiddleware(store)]
            if use_deferred:
                from deepclaw.middleware.tool_search import DeferredToolMiddleware
                middleware.insert(0, DeferredToolMiddleware())
            graph = create_agent(model=model, middleware=middleware, state_schema=StateSchema, system_prompt="测试本机工具")

            async def client():
                """模拟设备确认同一任务并回传内容。

                Args:
                    无。
                """
                async with asyncio.timeout(10):
                    while not (tasks := await store.tasks(device_id)):
                        await asyncio.sleep(0.02)
                    await store.event(device_id, "connection-a", DeviceEventRequest(task_id=tasks[0].id,
                        sequence=1, status="succeeded", result={"content": "本机内容"}))

            response, _ = await asyncio.gather(graph.ainvoke({"messages": [HumanMessage(content="读取文件")],
                "user_id": "alice", "device_id": device_id}, {"configurable": {"thread_id": "actual-thread"}}), client())
            assert "device_read_file" in bound_tools
            outputs = [message for message in response["messages"] if isinstance(message, ToolMessage)]
            assert len(outputs) == 1 and "本机内容" in outputs[0].content
            assert (await store.tasks(device_id))[0].thread_id == "actual-thread"
        finally:
            await store.engine.dispose()
    asyncio.run(run())
