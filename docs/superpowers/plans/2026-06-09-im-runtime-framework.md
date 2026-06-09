# IM Runtime Framework Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为本项目建立统一的多用户 IM 绑定与 runtime 框架，迁移并增强微信实现，并新增基于长连接的多用户 Feishu 驱动。

**Architecture:** 在 `deepclaw/web_backend/channels/` 下新增统一 binding/runtime 抽象，`ChannelService` 继续处理标准化消息流，平台差异下沉到 `weixin_clawbot` 和 `feishu` driver。运行态由统一 runtime 管理器负责，绑定数据持久化到 SQLModel，而不是继续把所有状态堆在 `channel_runtime_states`。

**Tech Stack:** FastAPI, SQLModel, asyncio, httpx, lark-oapi, pytest, Ruff

---

### Task 1: 引入统一 Binding 数据模型与存储接口

**Files:**
- Modify: `deepclaw/web_backend/channels/models.py`
- Modify: `deepclaw/web_backend/channels/store.py`
- Modify: `tests/test_channels_store.py`

- [ ] **Step 1: 编写失败测试**

```python
def test_binding_crud_and_session_binding_link():
    store = ChannelStore("sqlite:///:memory:")
    binding = store.create_binding(
        channel="feishu",
        owner_user_id="user_1",
        manager_user_id="user_1",
        display_name="我的飞书",
        credentials={"app_id": "cli_x", "app_secret": "sec_x"},
        config={"domain": "feishu", "streaming": True},
    )

    fetched = store.get_binding(binding.id)
    assert fetched is not None
    assert fetched.channel == "feishu"
    assert fetched.credentials["app_id"] == "cli_x"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/test_channels_store.py -q`
Expected: FAIL，提示 `create_binding` / `get_binding` 不存在。

- [ ] **Step 3: 最小实现模型与存储**

```python
class ChannelBinding(SQLModel, table=True):
    __tablename__ = "channel_bindings"

    id: int | None = Field(default=None, primary_key=True)
    channel: str = Field(index=True)
    owner_user_id: str = Field(index=True)
    manager_user_id: str = Field(index=True)
    status: str = Field(default="active", index=True)
    display_name: str | None = None
    credentials: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    config: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    runtime_state: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/test_channels_store.py -q`
Expected: PASS，`ChannelStore` 能完成 binding 的创建、查询、更新。

- [ ] **Step 5: 记录阶段完成**

Run: `git diff -- deepclaw/web_backend/channels/models.py deepclaw/web_backend/channels/store.py tests/test_channels_store.py`
Expected: 仅出现 binding 相关最小改动。

### Task 2: 为标准化消息与会话补充 binding 维度

**Files:**
- Modify: `deepclaw/web_backend/channels/models.py`
- Modify: `deepclaw/web_backend/channels/service.py`
- Modify: `tests/test_channels_service.py`

- [ ] **Step 1: 编写失败测试**

```python
def test_process_message_uses_binding_scoped_sessions(service_context):
    store = service_context["store"]
    service = ChannelService(
        store=store,
        agent_client=service_context["agent_client"],
        dispatcher=service_context["dispatcher"],
    )
    binding = store.create_binding(
        channel="weixin_clawbot",
        owner_user_id="user_1",
        manager_user_id="manager_1",
        credentials={"bot_token": "token_1"},
    )
    message = ChannelMessage(
        channel="weixin_clawbot",
        message_id="msg_1",
        channel_user_id="wx_user",
        channel_conversation_id="wx_chat",
        text="hello",
        user_id="user_1",
        manager_user_id="manager_1",
        binding_id=binding.id,
    )

    asyncio.run(service.process_message(message, FakeAdapter()))
    sessions = store.list_sessions()
    assert sessions[0].binding_id == binding.id
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/test_channels_service.py -q`
Expected: FAIL，提示 `binding_id` 字段缺失或未写入会话。

- [ ] **Step 3: 最小实现**

```python
class ChannelMessage(BaseModel):
    ...
    binding_id: int | None = None

class ChannelSession(SQLModel, table=True):
    ...
    binding_id: int | None = Field(default=None, index=True)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/test_channels_service.py -q`
Expected: PASS，会话按绑定实例隔离。

- [ ] **Step 5: 检查无回归**

Run: `uv run pytest tests/test_channels_dispatcher.py tests/test_channels_service.py -q`
Expected: PASS。

### Task 3: 抽取统一 runtime 管理器

**Files:**
- Create: `deepclaw/web_backend/channels/runtime_manager.py`
- Modify: `deepclaw/web_backend/channels/__init__.py`
- Modify: `tests/test_channels_lifespan.py`

- [ ] **Step 1: 编写失败测试**

```python
def test_runtime_manager_starts_and_stops_binding_runtime():
    manager = ChannelRuntimeManager()
    started = {}

    async def runner():
        started["value"] = True
        await asyncio.sleep(0)

    task = asyncio.run(manager.start("feishu:1", runner()))
    assert task is not None
    assert manager.is_running("feishu:1") is True
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/test_channels_lifespan.py -q`
Expected: FAIL，提示缺少 `ChannelRuntimeManager`。

- [ ] **Step 3: 最小实现**

```python
class ChannelRuntimeManager:
    def __init__(self):
        self._tasks: dict[str, asyncio.Task] = {}

    async def start(self, runtime_key: str, coroutine: Coroutine[Any, Any, Any]) -> asyncio.Task:
        existing = self._tasks.get(runtime_key)
        if existing is not None and not existing.done():
            return existing
        task = asyncio.create_task(coroutine)
        self._tasks[runtime_key] = task
        return task
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/test_channels_lifespan.py -q`
Expected: PASS。

- [ ] **Step 5: 检查接口**

Run: `uv run python -m py_compile deepclaw/web_backend/channels/runtime_manager.py`
Expected: 无输出。

### Task 4: 迁移并增强 Weixin 绑定模型

**Files:**
- Modify: `deepclaw/web_backend/channels/weixin_clawbot/router.py`
- Modify: `deepclaw/web_backend/channels/weixin_clawbot/runtime.py`
- Modify: `deepclaw/web_backend/channels/weixin_clawbot/lifespan.py`
- Modify: `deepclaw/web_backend/channels/weixin_clawbot/adapter.py`
- Modify: `tests/test_channels_router.py`
- Modify: `tests/test_channels_weixin_startup.py`
- Modify: `tests/test_channels_weixin_clawbot.py`

- [ ] **Step 1: 编写失败测试**

```python
def test_weixin_user_qrcode_creates_binding_instead_of_only_runtime_state(monkeypatch):
    store = ChannelStore("sqlite:///:memory:")
    client = build_channels_client(store=store, actor=CurrentActor(
        is_guest=False, user_id="manager_1", email="m@example.com", role="user"
    ), weixin_client=FakeWeixinClient())

    response = client.post("/api/channels/weixin-clawbot/users/user_1/qrcode")
    bindings = store.list_bindings(channel="weixin_clawbot", owner_user_id="user_1")

    assert response.status_code == 200
    assert len(bindings) == 1
    assert bindings[0].credentials == {}
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/test_channels_router.py::test_weixin_user_qrcode_creates_binding_instead_of_only_runtime_state -q`
Expected: FAIL。

- [ ] **Step 3: 最小实现**

```python
binding = channel_store.create_or_update_binding(
    channel=WEIXIN_CLAWBOT_CHANNEL,
    owner_user_id=user_id,
    manager_user_id=manager_user_id_from_actor(actor),
    display_name=f"Weixin ClawBot {user_id}",
    runtime_state={"qrcode": qrcode, "qrcode_url": qrcode_url},
)
```

- [ ] **Step 4: 运行增量测试**

Run: `uv run pytest tests/test_channels_router.py tests/test_channels_weixin_startup.py tests/test_channels_weixin_clawbot.py -q`
Expected: PASS，微信现有行为保持可用，同时绑定信息落到统一 binding 模型。

- [ ] **Step 5: 对齐 nanobot 能力边界**

Run: `uv run pytest tests/test_channels_weixin_clawbot.py -q`
Expected: PASS，覆盖 typing、context_token、消息状态、媒体相关路径。

### Task 5: 新增 Feishu 多用户长连接驱动

**Files:**
- Create: `deepclaw/web_backend/channels/feishu/settings.py`
- Create: `deepclaw/web_backend/channels/feishu/runtime.py`
- Create: `deepclaw/web_backend/channels/feishu/client.py`
- Modify: `deepclaw/web_backend/channels/feishu/adapter.py`
- Modify: `deepclaw/web_backend/channels/feishu/router.py`
- Modify: `deepclaw/web_backend/channels/router.py`
- Modify: `pyproject.toml`
- Create: `tests/test_channels_feishu.py`
- Modify: `tests/test_channels_router.py`

- [ ] **Step 1: 编写失败测试**

```python
def test_feishu_binding_create_and_start_runtime():
    store = ChannelStore("sqlite:///:memory:")
    binding = store.create_binding(
        channel="feishu",
        owner_user_id="user_1",
        manager_user_id="user_1",
        credentials={"app_id": "cli_x", "app_secret": "sec_x"},
        config={"domain": "feishu", "streaming": True, "group_policy": "mention"},
    )
    runtime = FeishuRuntime(binding=binding, service=FakeService())
    assert runtime.binding.id == binding.id
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/test_channels_feishu.py -q`
Expected: FAIL，缺少 `FeishuRuntime` 或 `lark_oapi` 封装。

- [ ] **Step 3: 最小实现**

```python
class FeishuRuntime:
    def __init__(self, *, binding: ChannelBinding, service: ChannelService):
        self.binding = binding
        self.service = service
        self.adapter = FeishuAdapter(binding=binding)
```

- [ ] **Step 4: 运行增量测试**

Run: `uv run pytest tests/test_channels_feishu.py tests/test_channels_router.py -q`
Expected: PASS，支持创建绑定、启动 runtime、解析 `im.message.receive_v1`、回发文本消息。

- [ ] **Step 5: 安装依赖声明校验**

Run: `uv run python - <<'PY'\nimport tomllib, pathlib\ntext = pathlib.Path('pyproject.toml').read_text(encoding='utf-8')\nprint('lark-oapi' in text)\nPY`
Expected: 输出 `True`。

### Task 6: 应用生命周期与渠道管理 API 收口

**Files:**
- Modify: `deepclaw/web_backend/lifespan.py`
- Modify: `deepclaw/web_backend/channels/common.py`
- Modify: `deepclaw/web_backend/channels/session_router.py`
- Modify: `tests/test_channels_lifespan.py`
- Modify: `tests/test_channels_router.py`
- Modify: `AGENTS.md`

- [ ] **Step 1: 编写失败测试**

```python
def test_channel_lifespan_starts_saved_feishu_and_weixin_bindings(monkeypatch):
    store = ChannelStore("sqlite:///:memory:")
    store.create_binding(
        channel="feishu",
        owner_user_id="user_1",
        manager_user_id="user_1",
        credentials={"app_id": "cli_x", "app_secret": "sec_x"},
    )
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/test_channels_lifespan.py -q`
Expected: FAIL。

- [ ] **Step 3: 最小实现**

```python
@asynccontextmanager
async def channel_lifespan() -> AsyncIterator[None]:
    manager = get_channel_runtime_manager()
    await start_saved_channel_runtimes(manager=manager, store=get_channel_store())
    try:
        yield
    finally:
        await manager.stop_all()
```

- [ ] **Step 4: 运行生命周期与路由测试**

Run: `uv run pytest tests/test_channels_lifespan.py tests/test_channels_router.py -q`
Expected: PASS。

- [ ] **Step 5: 更新文档**

Run: `rg -n "feishu|weixin_clawbot|channel_runtime_states|channel_bindings" AGENTS.md`
Expected: 文档与代码结构一致。

### Task 7: 全量验证与索引更新

**Files:**
- Modify: `docs/superpowers/plans/2026-06-09-im-runtime-framework.md`

- [ ] **Step 1: 运行 Python 语法检查**

Run: `uv run python -m py_compile deepclaw/web_backend/channels/models.py deepclaw/web_backend/channels/store.py deepclaw/web_backend/channels/service.py deepclaw/web_backend/channels/runtime_manager.py deepclaw/web_backend/channels/feishu/adapter.py deepclaw/web_backend/channels/feishu/router.py deepclaw/web_backend/channels/feishu/runtime.py deepclaw/web_backend/channels/weixin_clawbot/runtime.py deepclaw/web_backend/channels/weixin_clawbot/router.py deepclaw/web_backend/lifespan.py`
Expected: 无输出。

- [ ] **Step 2: 运行测试**

Run: `uv run pytest tests/test_channels_store.py tests/test_channels_service.py tests/test_channels_dispatcher.py tests/test_channels_router.py tests/test_channels_lifespan.py tests/test_channels_weixin_clawbot.py tests/test_channels_weixin_startup.py tests/test_channels_feishu.py -q`
Expected: PASS。

- [ ] **Step 3: 运行 Ruff**

Run: `uv run ruff check .`
Expected: `All checks passed!`

- [ ] **Step 4: 更新 CodeGraph 索引**

Run: `codegraph index --force`
Expected: 索引成功完成。

- [ ] **Step 5: 复核计划与结果**

Run: `git diff --stat`
Expected: 改动集中在 `channels`、测试、文档与依赖声明。
