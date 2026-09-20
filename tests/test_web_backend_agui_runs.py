from fastapi import FastAPI
from fastapi.testclient import TestClient

from deepclaw.web_backend.auth.dependencies import CurrentActor, get_current_actor
from deepclaw.web_backend.common.agui_runs import create_agui_run_router


class FakeRunManager:
    """测试用 AG-UI Run 管理器。"""

    def __init__(self):
        self.created = None
        self.resumed = None
        self.cancelled = None

    async def create(self, payload):
        """记录创建请求。\n\n        Args:\n            payload: AG-UI 输入。\n        """
        self.created = payload
        return {"runId": payload.run_id, "threadId": payload.thread_id, "status": "queued"}

    async def get_snapshot(self, run_id, user_id=None):
        """返回固定 Snapshot。\n\n        Args:\n            run_id: Run ID。\n        """
        if run_id != "run-1":
            return None
        return {"runId": run_id, "threadId": "thread-1", "status": "finished"}

    async def get_input(self, run_id, user_id=None):
        """返回固定输入。\n\n        Args:\n            run_id: Run ID。\n        """
        return None

    async def continue_run(self, run_id, payload, user_id=None):
        """记录恢复请求。\n\n        Args:\n            run_id: Run ID。\n            payload: AG-UI 输入。\n        """
        self.resumed = (run_id, payload)
        return {"runId": run_id, "threadId": payload.thread_id, "status": "queued"}

    async def cancel(self, run_id, user_id=None):
        """记录取消请求。\n\n        Args:\n            run_id: Run ID。\n        """
        self.cancelled = run_id
        return {"runId": run_id, "threadId": "thread-1", "status": "cancelled"}

    async def events(self, run_id, after=0, user_id=None):
        """返回可重放事件。\n\n        Args:\n            run_id: Run ID。\n            after: 事件序号。\n        """
        _ = after
        yield f"id: {run_id}:1\ndata: {{\"type\":\"RUN_STARTED\"}}\n\n"


def build_client(manager):
    """构建测试应用。\n\n    Args:\n        manager: 测试 Run 管理器。\n    """
    app = FastAPI()
    app.include_router(
        create_agui_run_router(
            manager,
            allowed_state_keys={"deep_thinking", "mcp_config"},
            tags=["test-agui"],
        )
    )
    app.dependency_overrides[get_current_actor] = lambda: CurrentActor(
        is_guest=True,
        user_id=None,
        email=None,
        role="guest",
    )
    return TestClient(app)


def payload(run_id="run-1"):
    """构造最小 RunAgentInput。\n\n    Args:\n        run_id: Run ID。\n    """
    return {
        "threadId": "thread-1",
        "runId": run_id,
        "state": {"deep_thinking": True, "user_id": "spoofed"},
        "messages": [{"id": "message-1", "role": "user", "content": "hello"}],
        "tools": [],
        "context": [],
        "forwardedProps": {},
    }


def test_create_run_overrides_user_id_with_trusted_actor():
    """验证创建 Run 时服务端覆盖客户端 user_id。"""
    manager = FakeRunManager()
    client = build_client(manager)

    response = client.post("/runs", json=payload())

    assert response.status_code == 202
    assert manager.created.state["user_id"] == "guest"
    assert manager.created.state["deep_thinking"] is True


def test_run_snapshot_events_resume_and_cancel():
    """验证 Run Snapshot、事件、恢复和取消端点。"""
    manager = FakeRunManager()
    client = build_client(manager)

    assert client.get("/runs/run-1").json()["status"] == "finished"
    assert client.get("/runs/missing").status_code == 404
    events = client.get("/runs/run-1/events")
    assert events.status_code == 200
    assert "RUN_STARTED" in events.text

    resumed = client.post("/runs/run-1/resume", json=payload())
    assert resumed.status_code == 202
    assert manager.resumed[0] == "run-1"

    cancelled = client.post("/runs/run-1/cancel")
    assert cancelled.status_code == 200
    assert manager.cancelled == "run-1"
