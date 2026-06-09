# IM 绑定中心 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把当前渠道能力升级为统一 IM 绑定中心，支持微信与飞书的多绑定管理、管理员总览，以及按 `binding_id` 隔离的 runtime 与会话。

**Architecture:** 后端继续以 `deepclaw/web_backend/channels/` 作为统一入口，但把“绑定集合”提升为一等对象：`ChannelStore` 负责多绑定持久化，`bindings_router` 暴露统一列表接口，各渠道 router 只处理本渠道的建绑、更新与删除。前端继续保留 `渠道管理` 单一入口，把现有微信专用页面重构为“我的绑定 / 管理员总览”双视角页面，并通过轻量 `node:test` 用例守住列表分组、筛选和状态汇总逻辑。

**Tech Stack:** FastAPI, SQLModel, asyncio, httpx, Next.js 15, React 19, TypeScript, node:test, pytest, Ruff

**Note:** 仓库 `AGENTS.md` 明确要求“未经用户明确要求，不要执行 `git add` / `git commit`”。因此本计划用“差异复核”替代提交步骤。

---

### Task 1: 把 ChannelBinding 存储改成真正的多绑定集合模型

**Files:**
- Modify: `deepclaw/web_backend/channels/models.py`
- Modify: `deepclaw/web_backend/channels/store.py`
- Modify: `tests/test_channels_store.py`

- [ ] **Step 1: 先写失败测试，锁定“同一用户同一渠道可有多条绑定”**

```python
def test_store_allows_multiple_bindings_for_same_owner_and_channel():
    store = ChannelStore("sqlite:///:memory:")
    first = store.create_binding(
        channel="feishu",
        owner_user_id="user_1",
        manager_user_id="user_1",
        display_name="市场部机器人",
        credentials={"app_id": "cli_a", "app_secret": "sec_a"},
        config={"domain": "feishu"},
    )
    second = store.create_binding(
        channel="feishu",
        owner_user_id="user_1",
        manager_user_id="user_1",
        display_name="客服值班号",
        credentials={"app_id": "cli_b", "app_secret": "sec_b"},
        config={"domain": "feishu"},
    )

    items = store.list_bindings(channel="feishu", owner_user_id="user_1")

    assert first.id != second.id
    assert [item.display_name for item in items] == ["客服值班号", "市场部机器人"]


def test_store_updates_only_target_binding():
    store = ChannelStore("sqlite:///:memory:")
    first = store.create_binding(
        channel="weixin_clawbot",
        owner_user_id="user_1",
        manager_user_id="user_1",
        display_name="张三主号",
        credentials={},
    )
    second = store.create_binding(
        channel="weixin_clawbot",
        owner_user_id="user_1",
        manager_user_id="user_1",
        display_name="李四代绑号",
        credentials={},
    )

    updated = store.update_binding(
        second.id,
        display_name="李四备用机",
        runtime_state={"status": "pending"},
    )

    deleted = store.delete_binding(second.id)
    remaining = store.list_bindings(channel="weixin_clawbot", owner_user_id="user_1")

    assert updated.display_name == "李四备用机"
    assert deleted is True
    assert store.get_binding(first.id).display_name == "张三主号"
    assert [item.display_name for item in remaining] == ["张三主号"]
```

- [ ] **Step 2: 运行测试，确认当前实现仍然是单绑定模型**

Run: `uv run pytest tests/test_channels_store.py::test_store_allows_multiple_bindings_for_same_owner_and_channel tests/test_channels_store.py::test_store_updates_only_target_binding -q`

Expected: FAIL，报错会集中在 `update_binding` 缺失，或 `upsert_binding()` 仍然按 `channel + owner_user_id` 覆盖已有记录。

- [ ] **Step 3: 最小实现多绑定存储接口，不再把 owner 视为唯一键**

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


def update_binding(
    self,
    binding_id: int,
    *,
    display_name: str | None = None,
    credentials: dict | None = None,
    config: dict | None = None,
    runtime_state: dict | None = None,
    status: str | None = None,
) -> ChannelBinding:
    with Session(self.engine) as session:
        binding = session.get(ChannelBinding, binding_id)
        if binding is None:
            raise ValueError("Channel binding not found")
        if display_name is not None:
            binding.display_name = display_name
        if credentials is not None:
            merged_credentials = dict(binding.credentials or {})
            merged_credentials.update(credentials)
            binding.credentials = merged_credentials
        if config is not None:
            merged_config = dict(binding.config or {})
            merged_config.update(config)
            binding.config = merged_config
        if runtime_state is not None:
            merged_runtime_state = dict(binding.runtime_state or {})
            merged_runtime_state.update(runtime_state)
            binding.runtime_state = merged_runtime_state
        if status is not None:
            binding.status = status
        binding.updated_at = utc_now()
        session.add(binding)
        session.commit()
        session.refresh(binding)
        return binding
```

- [ ] **Step 4: 重跑存储测试，确认集合模型成立**

Run: `uv run pytest tests/test_channels_store.py -q`

Expected: PASS，`ChannelStore` 可以对同一 `owner_user_id + channel` 持久化多条绑定，并且更新只影响指定 `binding_id`。

- [ ] **Step 5: 复核差异，确认没有残留新的 owner 唯一写法**

Run: `rg -n "upsert_binding\\(|owner_user_id == owner_user_id|channel\\s*==\\s*channel" deepclaw/web_backend/channels/store.py tests/test_channels_store.py`

Expected: 差异中保留新的 `create_binding / update_binding / list_bindings / delete_binding` 语义，不再出现“按 owner 合并第一条绑定”的核心路径。

### Task 2: 新增统一 bindings 列表接口，并把微信/飞书迁移到 binding_id 路径

**Files:**
- Create: `deepclaw/web_backend/channels/bindings_router.py`
- Modify: `deepclaw/web_backend/channels/router.py`
- Modify: `deepclaw/web_backend/channels/common.py`
- Modify: `deepclaw/web_backend/channels/feishu/router.py`
- Modify: `deepclaw/web_backend/channels/weixin_clawbot/router.py`
- Modify: `tests/test_channels_router.py`

- [ ] **Step 1: 先写失败测试，固定新的 REST 形状**

```python
def test_binding_list_route_respects_my_and_all_scope():
    store = ChannelStore("sqlite:///:memory:")
    store.create_binding(
        channel="feishu",
        owner_user_id="user_1",
        manager_user_id="user_1",
        display_name="市场部机器人",
        credentials={"app_id": "cli_a", "app_secret": "sec_a"},
    )
    store.create_binding(
        channel="weixin_clawbot",
        owner_user_id="user_2",
        manager_user_id="user_2",
        display_name="李四代绑号",
        credentials={},
    )

    user_client = build_channels_client(
        store=store,
        actor=CurrentActor(
            is_guest=False,
            user_id="user_1",
            email="user_1@example.com",
            role="user",
        ),
    )
    admin_client = build_channels_client(
        store=store,
        actor=CurrentActor(
            is_guest=False,
            user_id="admin_1",
            email="admin@example.com",
            role="admin",
        ),
    )

    user_response = user_client.get("/api/channels/bindings", params={"scope": "my"})
    admin_response = admin_client.get("/api/channels/bindings", params={"scope": "all"})

    assert [item["display_name"] for item in user_response.json()["items"]] == ["市场部机器人"]
    assert sorted(item["owner_user_id"] for item in admin_response.json()["items"]) == ["user_1", "user_2"]


def test_feishu_binding_routes_support_multiple_bindings_per_owner(monkeypatch):
    store = ChannelStore("sqlite:///:memory:")
    started = []

    async def fake_start_runtime(*, binding_id, store):
        started.append(binding_id)

    monkeypatch.setattr(
        "deepclaw.web_backend.channels.feishu.router.start_feishu_runtime",
        fake_start_runtime,
    )

    client = build_channels_client(
        store=store,
        actor=CurrentActor(
            is_guest=False,
            user_id="user_1",
            email="user_1@example.com",
            role="user",
        ),
    )

    first = client.post(
        "/api/channels/feishu/bindings",
        json={
            "owner_user_id": "user_1",
            "display_name": "市场部机器人",
            "app_id": "cli_a",
            "app_secret": "sec_a",
            "domain": "feishu",
            "group_policy": "mention",
            "streaming": True,
        },
    )
    second = client.post(
        "/api/channels/feishu/bindings",
        json={
            "owner_user_id": "user_1",
            "display_name": "客服值班号",
            "app_id": "cli_b",
            "app_secret": "sec_b",
            "domain": "feishu",
            "group_policy": "mention",
            "streaming": True,
        },
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["id"] != second.json()["id"]
    assert started == [first.json()["id"], second.json()["id"]]
```

- [ ] **Step 2: 运行路由测试，确认当前还是旧 `/users/{user_id}/binding` 单绑定接口**

Run: `uv run pytest tests/test_channels_router.py::test_binding_list_route_respects_my_and_all_scope tests/test_channels_router.py::test_feishu_binding_routes_support_multiple_bindings_per_owner -q`

Expected: FAIL，原因会是 `/api/channels/bindings` 不存在，且飞书当前接口仍是 `/feishu/users/{user_id}/binding`。

- [ ] **Step 3: 实现新的 bindings router，并为微信/飞书补 `binding_id` 路径**

```python
def create_channel_bindings_router(*, store: ChannelStore | None = None) -> APIRouter:
    router = APIRouter(tags=["channels"])
    channel_store = store or get_channel_store()

    @router.get("/bindings")
    async def list_bindings(
        scope: Literal["my", "all"] = "my",
        channel: str | None = None,
        owner_user_id: str | None = None,
        actor: CurrentActor = Depends(get_current_actor),
    ):
        if scope == "all" and not is_admin(actor):
            raise HTTPException(status_code=403, detail="只有管理员可以查看全量绑定。")
        manager_user_id = None if scope == "all" and is_admin(actor) else manager_user_id_from_actor(actor)
        items = [
            binding.model_dump()
            for binding in channel_store.list_bindings(
                channel=channel,
                owner_user_id=owner_user_id if is_admin(actor) else None,
                manager_user_id=manager_user_id,
            )
        ]
        return {"items": items, "total": len(items)}

    return router
```

```python
@router.post("/feishu/bindings")
async def create_feishu_binding(
    request: FeishuBindingRequest,
    actor: CurrentActor = Depends(get_current_actor),
):
    binding = channel_store.create_binding(
        channel="feishu",
        owner_user_id=request.owner_user_id,
        manager_user_id=manager_user_id_from_actor(actor),
        display_name=request.display_name,
        credentials={"app_id": request.app_id, "app_secret": request.app_secret},
        config={
            "domain": request.domain,
            "group_policy": request.group_policy,
            "streaming": request.streaming,
            "react_emoji": request.react_emoji,
            "done_emoji": request.done_emoji,
        },
        runtime_state={"status": "starting"},
    )
    await start_feishu_runtime(binding_id=binding.id, store=channel_store)
    return binding.model_dump()
```

```python
@router.post("/weixin-clawbot/bindings")
async def create_weixin_binding(
    request: WeixinBindingCreateRequest,
    actor: CurrentActor = Depends(get_current_actor),
):
    binding = channel_store.create_binding(
        channel=WEIXIN_CLAWBOT_CHANNEL,
        owner_user_id=request.owner_user_id,
        manager_user_id=manager_user_id_from_actor(actor),
        display_name=request.display_name,
        runtime_state={"status": "pending"},
    )
    return await _refresh_weixin_binding_qrcode(
        binding=binding,
        actor=actor,
        channel_store=channel_store,
        client=weixin_client or WeixinClawBotClient(),
    )


@router.delete("/feishu/bindings/{binding_id}")
async def delete_feishu_binding(
    binding_id: int,
    actor: CurrentActor = Depends(get_current_actor),
):
    binding = channel_store.get_binding(binding_id)
    ensure_binding_access(actor=actor, binding=binding, not_found_detail="Feishu binding not found")
    await stop_feishu_runtime(binding_id)
    deleted = channel_store.delete_binding(binding_id)
    return {"binding_id": binding_id, "deleted": deleted}
```

- [ ] **Step 4: 重跑路由测试，确认新接口成立且兼容层不破坏旧测试**

Run: `uv run pytest tests/test_channels_router.py -q`

Expected: PASS，新 `bindings` 列表接口与微信/飞书 `binding_id` 路径通过；旧路径若保留兼容层，也应继续通过现有未迁移测试。

- [ ] **Step 5: 语法检查新的 router 装配点**

Run: `uv run python -m py_compile deepclaw/web_backend/channels/bindings_router.py deepclaw/web_backend/channels/router.py deepclaw/web_backend/channels/feishu/router.py deepclaw/web_backend/channels/weixin_clawbot/router.py`

Expected: 无输出。

### Task 3: 让 runtime、消息处理与删除逻辑全部按 binding_id 工作

**Files:**
- Modify: `deepclaw/web_backend/channels/service.py`
- Modify: `deepclaw/web_backend/channels/feishu/runtime.py`
- Modify: `deepclaw/web_backend/channels/weixin_clawbot/runtime.py`
- Modify: `deepclaw/web_backend/channels/weixin_clawbot/lifespan.py`
- Modify: `tests/test_channels_service.py`
- Modify: `tests/test_channels_feishu.py`
- Modify: `tests/test_channels_weixin_startup.py`
- Modify: `tests/test_channels_lifespan.py`

- [ ] **Step 1: 先写失败测试，锁定 binding 级别的 runtime 与会话隔离**

```python
def test_process_message_routes_sessions_by_binding_id(service_context):
    store = service_context["store"]
    service = ChannelService(
        store=store,
        agent_client=service_context["agent_client"],
        dispatcher=service_context["dispatcher"],
    )
    first = store.create_binding(
        channel="feishu",
        owner_user_id="user_1",
        manager_user_id="user_1",
        display_name="市场部机器人",
        credentials={"app_id": "cli_a", "app_secret": "sec_a"},
    )
    second = store.create_binding(
        channel="feishu",
        owner_user_id="user_1",
        manager_user_id="user_1",
        display_name="客服值班号",
        credentials={"app_id": "cli_b", "app_secret": "sec_b"},
    )
    message_a = ChannelMessage(
        channel="feishu",
        message_id="msg_a",
        channel_user_id="ou_sender",
        channel_conversation_id="oc_same",
        binding_id=first.id,
        user_id="user_1",
        manager_user_id="user_1",
        text="hello a",
    )
    message_b = ChannelMessage(
        channel="feishu",
        message_id="msg_b",
        channel_user_id="ou_sender",
        channel_conversation_id="oc_same",
        binding_id=second.id,
        user_id="user_1",
        manager_user_id="user_1",
        text="hello b",
    )

    asyncio.run(service.process_message(message_a, FakeAdapter()))
    asyncio.run(service.process_message(message_b, FakeAdapter()))

    sessions = store.list_sessions(manager_user_id="user_1")
    assert len(sessions) == 2
    assert sorted(session.binding_id for session in sessions) == [first.id, second.id]
```

```python
def test_channel_lifespan_restarts_each_saved_binding(monkeypatch):
    store = ChannelStore("sqlite:///:memory:")
    feishu_binding = store.create_binding(
        channel="feishu",
        owner_user_id="user_1",
        manager_user_id="user_1",
        display_name="市场部机器人",
        credentials={"app_id": "cli_a", "app_secret": "sec_a"},
        runtime_state={"status": "stopped"},
    )
    weixin_binding = store.create_binding(
        channel="weixin_clawbot",
        owner_user_id="user_1",
        manager_user_id="user_1",
        display_name="张三主号",
        credentials={},
        runtime_state={"status": "pending", "qrcode": "qr_1"},
    )
    started = []

    async def fake_start_feishu_runtime(*, binding_id, store):
        started.append(("feishu", binding_id))

    async def fake_start_weixin_runtime(*, binding_id, store):
        started.append(("weixin_clawbot", binding_id))

    monkeypatch.setattr(
        "deepclaw.web_backend.channels.weixin_clawbot.lifespan.start_feishu_runtime",
        fake_start_feishu_runtime,
    )
    monkeypatch.setattr(
        "deepclaw.web_backend.channels.weixin_clawbot.lifespan.start_weixin_binding_runtime",
        fake_start_weixin_runtime,
    )
```

- [ ] **Step 2: 运行服务与生命周期测试，确认旧逻辑还依赖 user/state_key**

Run: `uv run pytest tests/test_channels_service.py::test_process_message_routes_sessions_by_binding_id tests/test_channels_lifespan.py::test_channel_lifespan_restarts_each_saved_binding -q`

Expected: FAIL，失败点通常会落在 lifecycle 只恢复旧微信状态、或 session 仍然复用单一会话。

- [ ] **Step 3: 最小实现 runtime_key、恢复逻辑与删除清理**

```python
def _routing_channel_user_id(self, message: ChannelMessage) -> str:
    if message.binding_id is not None:
        return f"binding:{message.binding_id}:{message.channel_user_id}"
    if not message.user_id:
        return message.channel_user_id
    return f"{message.user_id}:{message.channel_user_id}"


def _routing_conversation_id(self, message: ChannelMessage) -> str:
    if message.binding_id is not None:
        return f"binding:{message.binding_id}:{message.channel_conversation_id}"
    if not message.user_id:
        return message.channel_conversation_id
    return f"{message.user_id}:{message.channel_conversation_id}"
```

```python
def feishu_runtime_key(binding_id: int) -> str:
    return f"feishu:{binding_id}"


async def start_feishu_runtime(*, binding_id: int, store: ChannelStore | None = None):
    channel_store = store or get_channel_store()
    binding = channel_store.get_binding(binding_id)
    if binding is None:
        raise ValueError("Feishu binding not found")
    runtime = FeishuRuntime(binding=binding, store=channel_store)
    await get_channel_runtime_manager().start(feishu_runtime_key(binding_id), runtime.run_forever())
```

```python
async def start_saved_channel_runtimes(*, store: ChannelStore):
    for binding in store.list_bindings(channel="feishu"):
        if binding.status != "active":
            continue
        await start_feishu_runtime(binding_id=binding.id, store=store)
    for binding in store.list_bindings(channel="weixin_clawbot"):
        if binding.status not in {"active", "pending", "error"}:
            continue
        await start_weixin_binding_runtime(binding_id=binding.id, store=store)
```

- [ ] **Step 4: 重跑 runtime、服务、启动测试**

Run: `uv run pytest tests/test_channels_service.py tests/test_channels_feishu.py tests/test_channels_weixin_startup.py tests/test_channels_lifespan.py -q`

Expected: PASS，`binding_id` 维度隔离会话，Feishu/Weixin runtime 能按绑定独立恢复与停止。

- [ ] **Step 5: 复核 runtime 删除动作只影响目标绑定**

Run: `rg -n "stop_feishu_runtime|stop_weixin|binding_id|runtime_key" deepclaw/web_backend/channels/feishu deepclaw/web_backend/channels/weixin_clawbot deepclaw/web_backend/channels/service.py`

Expected: 删除与重启路径统一围绕 `binding_id`，不再只靠 `owner_user_id` 或 `state_key` 粗粒度定位。

### Task 4: 把前端 ChannelManagementView 重构成统一绑定中心

**Files:**
- Modify: `frontend/components/ChatInterface.tsx`
- Modify: `frontend/components/chat-interface/ChannelManagementView.tsx`
- Modify: `frontend/components/chat-interface/channelManagement.ts`
- Modify: `frontend/components/chat-interface/constants.ts`
- Modify: `frontend/components/chat-interface/types.ts`
- Modify: `frontend/components/chat-interface/auth.ts`
- Modify: `frontend/components/ChatInterface.module.css`
- Modify: `frontend/tests/channel-management.test.mjs`
- Modify: `frontend/tests/auth.test.mjs`

- [ ] **Step 1: 先补失败测试，把页面切换与分组逻辑收进纯函数**

```javascript
test('channel management groups bindings by channel and summarizes counts', () => {
  assert.equal(typeof channelManagementPkg.groupBindingsByChannel, 'function')
  assert.equal(typeof channelManagementPkg.summarizeChannelBindings, 'function')

  const bindings = [
    { id: 1, channel: 'weixin_clawbot', display_name: '张三主号', status: 'active', runtime_state: { status: 'connected' } },
    { id: 2, channel: 'weixin_clawbot', display_name: '李四代绑号', status: 'active', runtime_state: { status: 'pending' } },
    { id: 3, channel: 'feishu', display_name: '市场部机器人', status: 'error', runtime_state: { status: 'error' } },
  ]

  const groups = channelManagementPkg.groupBindingsByChannel(bindings)
  const weixinSummary = channelManagementPkg.summarizeChannelBindings(groups.weixin_clawbot)

  assert.equal(groups.weixin_clawbot.length, 2)
  assert.equal(groups.feishu.length, 1)
  assert.deepEqual(weixinSummary, {
    total: 2,
    connected: 1,
    pending: 1,
    error: 0,
  })
})

test('channel management filters admin overview rows by owner and channel', () => {
  assert.equal(typeof channelManagementPkg.filterBindingsForAdminOverview, 'function')

  const rows = channelManagementPkg.filterBindingsForAdminOverview(
    [
      { id: 1, channel: 'weixin_clawbot', owner_user_id: 'zhangsan', status: 'active', display_name: '张三主号', runtime_state: { status: 'connected' } },
      { id: 2, channel: 'feishu', owner_user_id: 'zhangsan', status: 'error', display_name: '市场部机器人', runtime_state: { status: 'error' } },
      { id: 3, channel: 'feishu', owner_user_id: 'lisi', status: 'active', display_name: '客服值班号', runtime_state: { status: 'connected' } },
    ],
    { ownerUserId: 'zhangsan', channel: 'feishu', status: '' }
  )

  assert.deepEqual(rows.map((item) => item.id), [2])
})

test('auth helpers expose channel admin capability only for admins', () => {
  const admin = authPkg.getActorCapabilities({
    isGuest: false,
    userId: 'admin_1',
    email: 'admin@example.com',
    role: 'admin',
  })
  const user = authPkg.getActorCapabilities({
    isGuest: false,
    userId: 'user_1',
    email: 'user@example.com',
    role: 'user',
  })

  assert.equal(admin.canManageChannelBindingsGlobally, true)
  assert.equal(user.canManageChannelBindingsGlobally, false)
})
```

- [ ] **Step 2: 运行前端 node:test 用例，确认辅助函数和权限字段都还不存在**

Run: `node --test frontend/tests/channel-management.test.mjs frontend/tests/auth.test.mjs`

Expected: FAIL，报错会集中在 `groupBindingsByChannel`、`summarizeChannelBindings`、`canManageChannelBindingsGlobally` 缺失。

- [ ] **Step 3: 实现统一绑定中心所需的类型、接口常量与视图逻辑**

```ts
export interface ChannelBindingRecord {
  id: number
  channel: 'weixin_clawbot' | 'feishu' | string
  owner_user_id: string
  manager_user_id: string
  status: string
  display_name: string | null
  credentials: Record<string, unknown>
  config: Record<string, unknown>
  runtime_state: Record<string, unknown>
  created_at: string
  updated_at: string
}

export interface ChannelBindingListResponse {
  items: ChannelBindingRecord[]
  total: number
}

export const CHANNEL_BINDINGS_API_PATH = '/api/channels/bindings'
export const FEISHU_BINDINGS_API_PATH = '/api/channels/feishu/bindings'
export const WEIXIN_BINDINGS_API_PATH = '/api/channels/weixin-clawbot/bindings'
```

```ts
export function groupBindingsByChannel(bindings: ChannelBindingRecord[]) {
  return bindings.reduce<Record<string, ChannelBindingRecord[]>>((acc, binding) => {
    const bucket = acc[binding.channel] || []
    bucket.push(binding)
    acc[binding.channel] = bucket
    return acc
  }, {})
}

export function summarizeChannelBindings(bindings: ChannelBindingRecord[]) {
  return bindings.reduce(
    (summary, binding) => {
      summary.total += 1
      const runtimeStatus = String(binding.runtime_state?.status || binding.status || '')
      if (runtimeStatus === 'connected') summary.connected += 1
      else if (runtimeStatus === 'error') summary.error += 1
      else summary.pending += 1
      return summary
    },
    { total: 0, connected: 0, pending: 0, error: 0 }
  )
}

export function filterBindingsForAdminOverview(
  bindings: ChannelBindingRecord[],
  filters: { ownerUserId: string; channel: string; status: string }
) {
  return bindings.filter((binding) => {
    if (filters.ownerUserId && binding.owner_user_id !== filters.ownerUserId) return false
    if (filters.channel && binding.channel !== filters.channel) return false
    if (filters.status) {
      const runtimeStatus = String(binding.runtime_state?.status || binding.status || '')
      if (runtimeStatus !== filters.status) return false
    }
    return true
  })
}
```

```tsx
<ChannelManagementView
  userId={currentUserId}
  actor={actor}
  requestJson={requestJson}
/>
```

```tsx
const canViewAdminScope = actor.role === 'admin'
const [scope, setScope] = useState<'my' | 'all'>('my')
const [bindings, setBindings] = useState<ChannelBindingRecord[]>([])
const groupedBindings = groupBindingsByChannel(bindings)
```

- [ ] **Step 4: 重跑前端 node:test，确认纯函数和权限逻辑稳定**

Run: `node --test frontend/tests/channel-management.test.mjs frontend/tests/auth.test.mjs`

Expected: PASS，绑定分组、状态汇总和管理员权限分支都通过。

- [ ] **Step 5: 做前端静态验证**

Run: `cd frontend && pnpm lint && pnpm build`

Expected: `tsc --noEmit` 通过，Next.js 生产构建成功，`ChannelManagementView` 在 TS 层没有残留旧的微信单绑定类型。

### Task 5: 补齐文档、回归测试与索引更新

**Files:**
- Modify: `AGENTS.md`
- Modify: `tests/test_channels_store.py`
- Modify: `tests/test_channels_router.py`
- Modify: `tests/test_channels_service.py`
- Modify: `tests/test_channels_feishu.py`
- Modify: `tests/test_channels_weixin_startup.py`
- Modify: `tests/test_channels_lifespan.py`
- Modify: `frontend/tests/channel-management.test.mjs`
- Modify: `docs/superpowers/specs/2026-06-09-im-binding-center-design.md`

- [ ] **Step 1: 在 AGENTS.md 中同步真实接口与前端渠道页事实**

```md
- `deepclaw/web_backend/channels/bindings_router.py`
  提供统一绑定列表接口，支持普通用户查看自己的绑定、管理员查看全量绑定。

- `deepclaw/web_backend/channels/feishu/router.py`
  负责飞书 binding 的创建、更新、删除与 runtime 启停。

- `deepclaw/web_backend/channels/weixin_clawbot/router.py`
  负责微信 binding 的创建、二维码刷新、状态查询与删除。

- 前端 `渠道管理` 页面已支持：
  - 我的绑定
  - 管理员总览
  - 微信与飞书的多绑定管理
```

- [ ] **Step 2: 跑后端回归测试，覆盖存储、路由、runtime、生命周期**

Run: `uv run pytest tests/test_channels_store.py tests/test_channels_router.py tests/test_channels_service.py tests/test_channels_feishu.py tests/test_channels_weixin_startup.py tests/test_channels_lifespan.py -q`

Expected: PASS，说明多绑定模型没有把现有渠道能力打散。

- [ ] **Step 3: 跑前端回归测试和构建**

Run: `node --test frontend/tests/channel-management.test.mjs frontend/tests/auth.test.mjs frontend/tests/branding.test.mjs frontend/tests/chat-runtime.test.mjs`

Expected: PASS，新增绑定中心逻辑没有破坏现有前端纯函数测试。

- [ ] **Step 4: 跑全量静态检查与语法检查**

Run: `uv run python -m py_compile deepclaw/web_backend/channels/models.py deepclaw/web_backend/channels/store.py deepclaw/web_backend/channels/bindings_router.py deepclaw/web_backend/channels/feishu/router.py deepclaw/web_backend/channels/weixin_clawbot/router.py deepclaw/web_backend/channels/service.py deepclaw/web_backend/channels/feishu/runtime.py deepclaw/web_backend/channels/weixin_clawbot/runtime.py deepclaw/web_backend/channels/weixin_clawbot/lifespan.py deepclaw/web_backend/lifespan.py`

Run: `uv run ruff check .`

Expected: 两条命令都通过，没有新的 Python 语法或风格回归。

- [ ] **Step 5: 更新 CodeGraph 索引并复核差异范围**

Run: `codegraph index --force`

Run: `git diff --stat`

Expected: CodeGraph 索引成功更新；最终差异主要集中在 `deepclaw/web_backend/channels/`、`frontend/components/chat-interface/`、对应测试与 `AGENTS.md`。
