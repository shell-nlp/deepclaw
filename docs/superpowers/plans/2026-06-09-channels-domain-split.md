# Channels Domain Split Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 `deepclaw/web_backend/channels/` 重构为按渠道域拆分的目录结构，保留共享会话接口，并将对外 API 调整为按渠道分组。

**Architecture:** 顶层 `channels` 仅保留共享模型、存储、服务、公共权限辅助和总装配路由；`feishu`、`dingtalk`、`weixin_clawbot` 各自拥有独立的 adapter/router，以及微信专属的 settings/client/runtime/lifespan/state 模块。应用层继续依赖顶层 `create_channels_router()` 与 `channel_lifespan()`，但内部实现改为委托子域模块。

**Tech Stack:** FastAPI, SQLModel, Pydantic, httpx, pytest, Ruff, CodeGraph.

**Constraints:** 不执行 `git add`、`git commit`、`git amend`。测试统一使用 `pytest`。所有结构变更完成后必须更新 `AGENTS.md`，并执行 `codegraph index --force`。

---

### Task 1: 先把新边界写成失败测试

**Files:**
- Modify: `tests/test_channels_router.py`
- Modify: `tests/test_channels_lifespan.py`
- Modify: `tests/test_channels_weixin_clawbot.py`
- Modify: `tests/test_channels_weixin_startup.py`
- Modify: `tests/test_channels_config.py`

- [ ] **Step 1: 先把路由测试改成新的按渠道分组导入与路径**

把 `tests/test_channels_router.py` 里的顶层导入与断言改为新的模块边界，优先覆盖这几类事实：

```python
from deepclaw.web_backend.channels.router import create_channels_router
from deepclaw.web_backend.channels.session_router import create_channel_sessions_router
from deepclaw.web_backend.channels.feishu.router import create_feishu_router
from deepclaw.web_backend.channels.dingtalk.router import create_dingtalk_router
from deepclaw.web_backend.channels.weixin_clawbot.router import (
    create_weixin_clawbot_router,
)


def test_channels_router_assembles_domain_routers():
    assert callable(create_channels_router)
    assert callable(create_channel_sessions_router)
    assert callable(create_feishu_router)
    assert callable(create_dingtalk_router)
    assert callable(create_weixin_clawbot_router)
```

同时把 webhook 和微信管理接口的请求路径统一保持为：

```python
response = client.post("/api/channels/feishu/events", json=payload)
response = client.post("/api/channels/dingtalk/events", json=payload)
response = client.post("/api/channels/weixin-clawbot/poll", json=payload)
response = client.get("/api/channels/sessions")
```

- [ ] **Step 2: 运行 router 测试并确认因新模块不存在而失败**

Run:

```bash
uv run pytest tests/test_channels_router.py -q
```

Expected: FAIL，错误应指向 `channels.session_router`、`channels.feishu.router`、`channels.weixin_clawbot.router` 等模块尚未创建，而不是测试语法错误。

- [ ] **Step 3: 把微信 settings 的测试改成新导入位置**

在 `tests/test_channels_config.py` 中，保留公共配置仍从顶层导入，但微信配置改为专属模块导入：

```python
from deepclaw.web_backend.channels.config import channel_gateway_settings
from deepclaw.web_backend.channels.weixin_clawbot.settings import (
    weixin_clawbot_settings,
)
```

并显式断言：

```python
assert channel_gateway_settings.CHANNEL_AGENT_API_URL == (
    "http://127.0.0.1:7869/api/agent/general_api"
)
assert weixin_clawbot_settings.WEIXIN_CLAWBOT_API_BASE_URL == (
    "https://ilinkai.weixin.qq.com"
)
```

- [ ] **Step 4: 把微信 client/adapter/runtime 测试改成新导入位置**

把这两组导入迁到新模块名：

```python
from deepclaw.web_backend.channels.weixin_clawbot.adapter import (
    WeixinClawBotAdapter,
)
from deepclaw.web_backend.channels.weixin_clawbot.client import (
    WeixinClawBotClient,
)
```

```python
from deepclaw.web_backend.channels.weixin_clawbot.runtime import (
    WeixinClawBotRuntime,
    fetch_startup_qrcode,
)
from deepclaw.web_backend.channels.weixin_clawbot.state import (
    weixin_clawbot_user_state_key,
)
```

- [ ] **Step 5: 把微信 lifespan 测试改成新模块路径**

把 `tests/test_channels_lifespan.py` 顶部改为：

```python
import asyncio

from deepclaw.web_backend.channels.weixin_clawbot import lifespan as weixin_lifespan_module
```

并让 monkeypatch 直接打到新模块：

```python
monkeypatch.setattr(
    weixin_lifespan_module,
    "weixin_clawbot_settings",
    FakeSettings(),
)
monkeypatch.setattr(
    weixin_lifespan_module,
    "WeixinClawBotRuntime",
    FakeRuntime,
)
```

- [ ] **Step 6: 运行这组测试并确认红灯**

Run:

```bash
uv run pytest tests/test_channels_router.py tests/test_channels_config.py tests/test_channels_weixin_clawbot.py tests/test_channels_weixin_startup.py tests/test_channels_lifespan.py -q
```

Expected: FAIL，失败原因为新模块尚未落地。

### Task 2: 建立共享层新边界并精简顶层装配

**Files:**
- Create: `deepclaw/web_backend/channels/common.py`
- Create: `deepclaw/web_backend/channels/session_router.py`
- Modify: `deepclaw/web_backend/channels/router.py`
- Modify: `deepclaw/web_backend/channels/service.py`
- Modify: `deepclaw/web_backend/channels/__init__.py`

- [ ] **Step 1: 新建 `common.py`，先承接当前 router 里的共享权限和会话访问辅助函数**

在 `deepclaw/web_backend/channels/common.py` 中放入这些现有共享函数，保持签名尽量不变：

```python
from typing import Any

from fastapi import HTTPException

from deepclaw.web_backend.auth.dependencies import CurrentActor
from deepclaw.web_backend.channels.models import ChannelSession
from deepclaw.web_backend.channels.store import ChannelStore
from deepclaw.web_backend.channels.weixin_clawbot.state import (
    weixin_clawbot_user_id_from_state_key,
)


GUEST_MANAGER_USER_ID = "guest"


def is_admin(actor: CurrentActor) -> bool:
    return (not actor.is_guest) and actor.role == "admin"


def manager_user_id_from_actor(actor: CurrentActor) -> str:
    if actor.is_guest:
        return GUEST_MANAGER_USER_ID
    if actor.user_id:
        return actor.user_id
    raise HTTPException(status_code=403, detail="当前账号缺少可用的 user_id。")
```

把现有 `_runtime_state_manager_user_id()`、`_session_manager_user_id()`、`ensure_runtime_state_access()`、`ensure_session_access()` 一并迁入该文件。

- [ ] **Step 2: 为共享会话接口创建独立 router**

新建 `deepclaw/web_backend/channels/session_router.py`：

```python
from fastapi import APIRouter, Depends, HTTPException

from deepclaw.web_backend.auth.dependencies import CurrentActor, get_current_actor
from deepclaw.web_backend.channels.common import (
    ensure_session_access,
    is_admin,
    manager_user_id_from_actor,
    session_manager_user_id,
)
from deepclaw.web_backend.channels.models import (
    ChannelSessionList,
    ChannelSessionRead,
    ChannelSessionUpdate,
)
from deepclaw.web_backend.channels.store import ChannelStore, get_channel_store


def create_channel_sessions_router(*, store: ChannelStore | None = None) -> APIRouter:
    router = APIRouter(tags=["channels"])
    channel_store = store or get_channel_store()

    @router.get("/sessions", response_model=ChannelSessionList)
    async def list_sessions(actor: CurrentActor = Depends(get_current_actor)):
        sessions = [
            ChannelSessionRead.model_validate(item)
            for item in channel_store.list_sessions()
            if is_admin(actor)
            or session_manager_user_id(channel_store, item) == manager_user_id_from_actor(actor)
        ]
        return ChannelSessionList(items=sessions, total=len(sessions))

    @router.patch("/sessions/{session_id}", response_model=ChannelSessionRead)
    async def update_session(
        session_id: str,
        update: ChannelSessionUpdate,
        actor: CurrentActor = Depends(get_current_actor),
    ):
        channel_session = channel_store.get_session_by_session_id(session_id)
        if channel_session is None:
            raise HTTPException(status_code=404, detail="Channel session not found")
        ensure_session_access(
            actor=actor,
            channel_store=channel_store,
            channel_session=channel_session,
        )
        if update.reply_mode is None:
            return ChannelSessionRead.model_validate(channel_session)
        channel_session = channel_store.update_session_reply_mode(
            session_id,
            update.reply_mode,
        )
        return ChannelSessionRead.model_validate(channel_session)

    return router
```

- [ ] **Step 3: 调整 `ChannelService` 读取微信默认回复模式的依赖边界**

把 `deepclaw/web_backend/channels/service.py` 的微信配置导入改成：

```python
from deepclaw.web_backend.channels.weixin_clawbot.settings import (
    weixin_clawbot_settings,
)
```

保留 `_default_reply_mode()` 行为不变：

```python
def _default_reply_mode(self, message: ChannelMessage) -> str:
    if message.channel == "weixin_clawbot":
        return weixin_clawbot_settings.WEIXIN_CLAWBOT_DEFAULT_REPLY_MODE
    return "final"
```

- [ ] **Step 4: 把顶层 `router.py` 改成纯装配器**

将 `deepclaw/web_backend/channels/router.py` 收缩为：

```python
from fastapi import APIRouter

from deepclaw.web_backend.channels.dingtalk.router import create_dingtalk_router
from deepclaw.web_backend.channels.feishu.router import create_feishu_router
from deepclaw.web_backend.channels.service import ChannelService
from deepclaw.web_backend.channels.session_router import create_channel_sessions_router
from deepclaw.web_backend.channels.store import ChannelStore, get_channel_store
from deepclaw.web_backend.channels.weixin_clawbot.client import WeixinClawBotClient
from deepclaw.web_backend.channels.weixin_clawbot.router import (
    create_weixin_clawbot_router,
)


def create_channels_router(
    *,
    store: ChannelStore | None = None,
    service: ChannelService | None = None,
    weixin_client: WeixinClawBotClient | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/api/channels")
    channel_store = store or get_channel_store()
    channel_service = service or ChannelService(store=channel_store)

    router.include_router(create_channel_sessions_router(store=channel_store))
    router.include_router(create_feishu_router(store=channel_store, service=channel_service))
    router.include_router(create_dingtalk_router(store=channel_store, service=channel_service))
    router.include_router(
        create_weixin_clawbot_router(
            store=channel_store,
            service=channel_service,
            weixin_client=weixin_client,
        )
    )
    return router
```

- [ ] **Step 5: 更新顶层导出**

把 `deepclaw/web_backend/channels/__init__.py` 改成只暴露共享出口：

```python
from deepclaw.web_backend.channels.agent_client import AgentClient
from deepclaw.web_backend.channels.config import channel_gateway_settings
from deepclaw.web_backend.channels.service import ChannelService
from deepclaw.web_backend.channels.store import ChannelStore, get_channel_store
from deepclaw.web_backend.channels.weixin_clawbot.lifespan import channel_lifespan
from deepclaw.web_backend.channels.weixin_clawbot.settings import (
    weixin_clawbot_settings,
)
from deepclaw.web_backend.channels.router import create_channels_router
```

- [ ] **Step 6: 运行共享层相关测试，确认它们仍然失败但失败点已经移动到缺失的渠道子模块**

Run:

```bash
uv run pytest tests/test_channels_router.py tests/test_channels_config.py tests/test_channels_service.py -q
```

Expected: FAIL，`service` 与 `config` 相关断言应可导入，剩余失败集中在 `feishu`、`dingtalk`、`weixin_clawbot` 子模块尚未创建。

### Task 3: 拆出 Feishu 与 DingTalk 子域

**Files:**
- Create: `deepclaw/web_backend/channels/feishu/__init__.py`
- Create: `deepclaw/web_backend/channels/feishu/adapter.py`
- Create: `deepclaw/web_backend/channels/feishu/router.py`
- Create: `deepclaw/web_backend/channels/dingtalk/__init__.py`
- Create: `deepclaw/web_backend/channels/dingtalk/adapter.py`
- Create: `deepclaw/web_backend/channels/dingtalk/router.py`
- Modify: `tests/test_channels_router.py`

- [ ] **Step 1: 复制现有 Feishu adapter 到新域目录**

`deepclaw/web_backend/channels/feishu/adapter.py` 直接保留当前实现：

```python
import uuid

from deepclaw.web_backend.channels.models import ChannelMessage


class FeishuAdapter:
    channel = "feishu"

    async def parse_event(self, payload: dict) -> ChannelMessage:
        return ChannelMessage(
            channel=self.channel,
            message_id=str(payload["message_id"]),
            channel_user_id=str(payload["channel_user_id"]),
            channel_conversation_id=str(payload["channel_conversation_id"]),
            text=str(payload.get("text", "")),
            message_type=str(payload.get("message_type", "text")),
            raw=payload,
        )

    async def send_message(self, message: ChannelMessage, text: str) -> str:
        return f"feishu_reply_{uuid.uuid4().hex}"

    async def edit_message(self, reply_message_id: str, text: str) -> None:
        return None
```

- [ ] **Step 2: 为 Feishu 建立独立 router**

`deepclaw/web_backend/channels/feishu/router.py`：

```python
from fastapi import APIRouter, BackgroundTasks

from deepclaw.web_backend.channels.feishu.adapter import FeishuAdapter
from deepclaw.web_backend.channels.service import ChannelService
from deepclaw.web_backend.channels.store import ChannelStore, get_channel_store


def create_feishu_router(
    *,
    store: ChannelStore | None = None,
    service: ChannelService | None = None,
) -> APIRouter:
    router = APIRouter(tags=["channels"])
    channel_store = store or get_channel_store()
    channel_service = service or ChannelService(store=channel_store)

    @router.post("/feishu/events")
    async def feishu_events(payload: dict, background_tasks: BackgroundTasks):
        adapter = FeishuAdapter()
        message = await adapter.parse_event(payload)
        background_tasks.add_task(channel_service.process_message, message, adapter)
        return {"status": "accepted"}

    return router
```

- [ ] **Step 3: 对 DingTalk 做对称拆分**

`deepclaw/web_backend/channels/dingtalk/adapter.py` 与 `router.py` 保持与 Feishu 对称，只将类名和路径改为 DingTalk：

```python
class DingTalkAdapter:
    channel = "dingtalk"
```

```python
@router.post("/dingtalk/events")
async def dingtalk_events(payload: dict, background_tasks: BackgroundTasks):
    adapter = DingTalkAdapter()
    message = await adapter.parse_event(payload)
    background_tasks.add_task(channel_service.process_message, message, adapter)
    return {"status": "accepted"}
```

- [ ] **Step 4: 为两个子域添加 `__init__.py` 导出**

```python
from deepclaw.web_backend.channels.feishu.adapter import FeishuAdapter

__all__ = ["FeishuAdapter"]
```

```python
from deepclaw.web_backend.channels.dingtalk.adapter import DingTalkAdapter

__all__ = ["DingTalkAdapter"]
```

- [ ] **Step 5: 跑 Feishu/DingTalk 路由测试，确认这两块转绿**

Run:

```bash
uv run pytest tests/test_channels_router.py -q -k "feishu or dingtalk or sessions"
```

Expected: PASS，Feishu webhook、DingTalk webhook 和共享 sessions 的测试通过；失败若存在，应只剩微信相关模块缺失。

### Task 4: 拆出 Weixin ClawBot 子域

**Files:**
- Create: `deepclaw/web_backend/channels/weixin_clawbot/__init__.py`
- Create: `deepclaw/web_backend/channels/weixin_clawbot/settings.py`
- Create: `deepclaw/web_backend/channels/weixin_clawbot/client.py`
- Create: `deepclaw/web_backend/channels/weixin_clawbot/adapter.py`
- Create: `deepclaw/web_backend/channels/weixin_clawbot/state.py`
- Create: `deepclaw/web_backend/channels/weixin_clawbot/runtime.py`
- Create: `deepclaw/web_backend/channels/weixin_clawbot/lifespan.py`
- Create: `deepclaw/web_backend/channels/weixin_clawbot/router.py`
- Create: `deepclaw/web_backend/channels/weixin_clawbot/schemas.py`
- Modify: `deepclaw/web_backend/channels/schemas.py`

- [ ] **Step 1: 先创建微信专属 settings 模块，并把顶层 `config.py` 收缩为纯公共配置**

新建 `weixin_clawbot/settings.py`：

```python
from typing import Literal

from dotenv import find_dotenv, load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict


env_path = find_dotenv(filename=".env", raise_error_if_not_found=True)
load_dotenv()


class WeixinClawBotSettings(BaseSettings):
    WEIXIN_CLAWBOT_API_BASE_URL: str = "https://ilinkai.weixin.qq.com"
    WEIXIN_CLAWBOT_REQUEST_TIMEOUT_SECONDS: float = 10.0
    WEIXIN_CLAWBOT_PRINT_QRCODE_ON_STARTUP: bool = True
    WEIXIN_CLAWBOT_AUTO_POLL_ON_STARTUP: bool = True
    WEIXIN_CLAWBOT_LOGIN_POLL_INTERVAL_SECONDS: float = 2.0
    WEIXIN_CLAWBOT_MESSAGE_POLL_INTERVAL_SECONDS: float = 1.0
    WEIXIN_CLAWBOT_DEFAULT_REPLY_MODE: Literal["final", "streaming"] = "streaming"

    model_config = SettingsConfigDict(
        env_file=str(env_path),
        env_file_encoding="utf-8",
        extra="ignore",
    )


def get_weixin_clawbot_settings() -> WeixinClawBotSettings:
    return WeixinClawBotSettings()


weixin_clawbot_settings = get_weixin_clawbot_settings()
```

把顶层 `config.py` 删掉微信设置，仅保留：

```python
class ChannelGatewaySettings(BaseSettings):
    CHANNEL_AGENT_API_URL: str = "http://127.0.0.1:7869/api/agent/general_api"
```

- [ ] **Step 2: 将微信 client 从旧 adapter 文件中独立出来**

`deepclaw/web_backend/channels/weixin_clawbot/client.py` 放请求常量、错误类、`base_info()`、`make_headers()`、`WeixinClawBotClient`：

```python
class WeixinClawBotRequestError(RuntimeError):
    pass


class WeixinClawBotRequestTimeoutError(WeixinClawBotRequestError):
    pass
```

```python
class WeixinClawBotClient:
    def __init__(self, *, base_url: str | None = None, request_json: RequestJson | None = None):
        self.base_url = (
            base_url or weixin_clawbot_settings.WEIXIN_CLAWBOT_API_BASE_URL
        ).rstrip("/")
        self.request_json = request_json or self._request_json
```

保留现有 `fetch_login_qrcode()`、`get_qrcode_status()`、`get_updates()`、`get_config()`、`send_typing()`、`send_message()`、`_request_json()` 的具体请求体与路径。

- [ ] **Step 3: 将微信 adapter 独立为纯消息适配层**

`deepclaw/web_backend/channels/weixin_clawbot/adapter.py` 只保留：

```python
from deepclaw.web_backend.channels.models import ChannelMessage
from deepclaw.web_backend.channels.weixin_clawbot.client import (
    MESSAGE_STATE_FINISH,
    MESSAGE_STATE_GENERATING,
    WeixinClawBotClient,
)


CHANNEL = "weixin_clawbot"
```

并沿用现有 `WeixinClawBotAdapter` 的：

- `parse_update_message()`
- `iter_text_messages()`
- `send_message()`
- `start_message()`
- `edit_message()`
- `finish_message()`
- `start_typing()`
- `stop_typing()`

不要在这一步改行为，只改模块边界。

- [ ] **Step 4: 将微信 runtime 状态纯函数独立到 `state.py`**

新建 `state.py`，至少包含：

```python
def weixin_clawbot_user_state_key(user_id: str) -> str:
    return f"user:{user_id}"


def weixin_clawbot_user_id_from_state_key(state_key: str) -> str | None:
    if not state_key.startswith("user:"):
        return None
    return state_key.removeprefix("user:") or None
```

以及现有逻辑里的：

- `weixin_clawbot_manager_user_id_from_state()`
- `mask_token()`
- `runtime_state_manager_user_id()`

这些函数要从原先顶层 `router.py` / `weixin_startup.py` 抽出来，而不是重新发明。

- [ ] **Step 5: 将微信 runtime 与 startup 逻辑移入 `runtime.py`**

`deepclaw/web_backend/channels/weixin_clawbot/runtime.py` 要包含：

```python
RUNTIME_STATE_KEY = "default"
```

```python
async def fetch_startup_qrcode(
    *,
    client: WeixinClawBotClient | None = None,
) -> dict[str, str | dict]:
    client = client or WeixinClawBotClient()
    data = await client.fetch_login_qrcode(local_token_list=[])
    return {
        "qrcode": str(data.get("qrcode") or ""),
        "qrcode_url": str(data.get("qrcode_img_content") or data.get("qrcode") or ""),
        "raw": data,
    }
```

并迁入 `WeixinClawBotRuntime` 当前行为：

- 读取 `ChannelStore` 中持久化的 `bot_token`、`base_url`、`get_updates_buf`
- `run_once()` 中处理二维码登录和 token 失效回退
- `run_forever()` 中根据 settings 的时间间隔轮询

- [ ] **Step 6: 将微信 runtime 任务表与自动恢复逻辑移入 `lifespan.py`**

`deepclaw/web_backend/channels/weixin_clawbot/lifespan.py` 保持公开函数名稳定：

```python
@asynccontextmanager
async def channel_lifespan() -> AsyncIterator[None]:
    channel_store = get_channel_store()
    if weixin_clawbot_settings.WEIXIN_CLAWBOT_AUTO_POLL_ON_STARTUP:
        await start_saved_weixin_clawbot_runtimes(store=channel_store)
    try:
        yield
    finally:
        await stop_weixin_clawbot_runtimes()
```

保留：

- `start_saved_weixin_clawbot_runtimes()`
- `start_weixin_clawbot_runtime()`
- `stop_weixin_clawbot_runtimes()`
- `stop_weixin_clawbot_runtime()`

- [ ] **Step 7: 将微信 schema 独立出来**

把原 `deepclaw/web_backend/channels/schemas.py` 的微信请求/响应模型迁入：

```python
class WeixinClawBotPollRequest(BaseModel):
    bot_token: str
    get_updates_buf: str = ""
```

```python
class WeixinClawBotBoundUserDeleteResponse(BaseModel):
    user_id: str
    deleted: bool
```

把顶层 `deepclaw/web_backend/channels/schemas.py` 改成兼容转发文件，内容固定为：

```python
from deepclaw.web_backend.channels.weixin_clawbot.schemas import (
    WeixinClawBotBoundUserDeleteResponse,
    WeixinClawBotBoundUserList,
    WeixinClawBotBoundUserRead,
    WeixinClawBotPollRequest,
    WeixinClawBotQRCodeRequest,
)

__all__ = [
    "WeixinClawBotBoundUserDeleteResponse",
    "WeixinClawBotBoundUserList",
    "WeixinClawBotBoundUserRead",
    "WeixinClawBotPollRequest",
    "WeixinClawBotQRCodeRequest",
]
```

- [ ] **Step 8: 建立微信专属 router**

`deepclaw/web_backend/channels/weixin_clawbot/router.py` 负责：

- `POST /weixin-clawbot/qrcode`
- `GET /weixin-clawbot/qrcode/status`
- `POST /weixin-clawbot/users/{user_id}/qrcode`
- `GET /weixin-clawbot/users/{user_id}/qrcode/status`
- `GET /weixin-clawbot/users`
- `DELETE /weixin-clawbot/users/{user_id}`
- `POST /weixin-clawbot/poll`

先复用当前逻辑，只把依赖切换为新模块：

```python
from deepclaw.web_backend.channels.common import manager_user_id_from_actor
from deepclaw.web_backend.channels.store import ChannelStore, get_channel_store
from deepclaw.web_backend.channels.weixin_clawbot.adapter import (
    CHANNEL as WEIXIN_CLAWBOT_CHANNEL,
    WeixinClawBotAdapter,
)
from deepclaw.web_backend.channels.weixin_clawbot.client import (
    WeixinClawBotClient,
    WeixinClawBotRequestError,
    WeixinClawBotRequestTimeoutError,
)
from deepclaw.web_backend.channels.weixin_clawbot.lifespan import (
    start_weixin_clawbot_runtime,
    stop_weixin_clawbot_runtime,
)
from deepclaw.web_backend.channels.weixin_clawbot.schemas import (
    WeixinClawBotBoundUserDeleteResponse,
    WeixinClawBotBoundUserList,
    WeixinClawBotBoundUserRead,
    WeixinClawBotPollRequest,
    WeixinClawBotQRCodeRequest,
)
from deepclaw.web_backend.channels.weixin_clawbot.state import (
    runtime_state_manager_user_id,
    weixin_clawbot_user_id_from_state_key,
    weixin_clawbot_user_state_key,
)
```

- [ ] **Step 9: 跑微信相关测试直到转绿**

Run:

```bash
uv run pytest tests/test_channels_config.py tests/test_channels_weixin_clawbot.py tests/test_channels_weixin_startup.py tests/test_channels_lifespan.py tests/test_channels_router.py -q
```

Expected: PASS。

### Task 5: 清理旧目录、补齐应用装配与文档、完成验证

**Files:**
- Delete: `deepclaw/web_backend/channels/adapters/feishu.py`
- Delete: `deepclaw/web_backend/channels/adapters/dingtalk.py`
- Delete: `deepclaw/web_backend/channels/adapters/weixin_clawbot.py`
- Delete: `deepclaw/web_backend/channels/weixin_startup.py`
- Modify: `deepclaw/web_backend/channels/lifespan.py`
- Modify: `deepclaw/web_backend/channels/config.py`
- Modify: `deepclaw/web_backend/lifespan.py`
- Modify: `deepclaw/web_backend/app.py`
- Modify: `tests/test_web_backend_app.py`
- Modify: `AGENTS.md`

- [ ] **Step 1: 删除已迁移的旧实现文件，并清理残余导入**

删除：

```text
deepclaw/web_backend/channels/adapters/feishu.py
deepclaw/web_backend/channels/adapters/dingtalk.py
deepclaw/web_backend/channels/adapters/weixin_clawbot.py
deepclaw/web_backend/channels/weixin_startup.py
```

同时把 `deepclaw/web_backend/channels/adapters/__init__.py` 删除，避免残留空命名空间。

- [ ] **Step 2: 确认应用层仍然只依赖顶层公共出口**

`deepclaw/web_backend/app.py` 保持：

```python
from deepclaw.web_backend.channels.router import create_channels_router
```

`deepclaw/web_backend/lifespan.py` 保持：

```python
from deepclaw.web_backend.channels.lifespan import channel_lifespan
```

把 `deepclaw/web_backend/channels/lifespan.py` 改成固定薄封装：

```python
from deepclaw.web_backend.channels.weixin_clawbot.lifespan import channel_lifespan

__all__ = ["channel_lifespan"]
```

这样 `web_backend/lifespan.py` 无须改动导入路径，且顶层公共出口保持稳定。

- [ ] **Step 3: 更新 `AGENTS.md` 的 channels 结构说明**

把原先对 `deepclaw/web_backend/channels/` 的描述改为按域拆分后的真实结构，例如：

```md
- `deepclaw/web_backend/channels/`
  渠道共享模型、会话存储、消息处理服务、共享会话接口与总装配入口。

- `deepclaw/web_backend/channels/feishu/`
  飞书渠道适配与事件路由。

- `deepclaw/web_backend/channels/dingtalk/`
  钉钉渠道适配与事件路由。

- `deepclaw/web_backend/channels/weixin_clawbot/`
  微信 ClawBot 专属适配器、API 客户端、运行时、生命周期、状态辅助与管理路由。
```

- [ ] **Step 4: 更新 app 级测试与任何仍引用旧模块路径的测试**

执行搜索：

```bash
rg -n "channels\\.adapters|channels\\.weixin_startup|channels\\.schemas|weixin_clawbot_settings" tests deepclaw
```

将残余旧路径替换为新路径，重点确认 `tests/test_web_backend_app.py` 只依赖 `create_channels_router` 顶层出口，不直接碰内部子模块。

- [ ] **Step 5: 运行精确验证**

Run:

```bash
uv run python -m py_compile deepclaw/web_backend/channels/__init__.py deepclaw/web_backend/channels/common.py deepclaw/web_backend/channels/config.py deepclaw/web_backend/channels/router.py deepclaw/web_backend/channels/session_router.py deepclaw/web_backend/channels/service.py deepclaw/web_backend/channels/feishu/adapter.py deepclaw/web_backend/channels/feishu/router.py deepclaw/web_backend/channels/dingtalk/adapter.py deepclaw/web_backend/channels/dingtalk/router.py deepclaw/web_backend/channels/weixin_clawbot/settings.py deepclaw/web_backend/channels/weixin_clawbot/client.py deepclaw/web_backend/channels/weixin_clawbot/adapter.py deepclaw/web_backend/channels/weixin_clawbot/state.py deepclaw/web_backend/channels/weixin_clawbot/runtime.py deepclaw/web_backend/channels/weixin_clawbot/lifespan.py deepclaw/web_backend/channels/weixin_clawbot/router.py deepclaw/web_backend/channels/weixin_clawbot/schemas.py deepclaw/web_backend/app.py deepclaw/web_backend/lifespan.py
```

Expected: 无输出，退出码 0。

- [ ] **Step 6: 运行 channels 相关测试**

Run:

```bash
uv run pytest tests/test_channels_router.py tests/test_channels_config.py tests/test_channels_service.py tests/test_channels_store.py tests/test_channels_dispatcher.py tests/test_channels_weixin_clawbot.py tests/test_channels_weixin_startup.py tests/test_channels_lifespan.py tests/test_web_backend_app.py -q
```

Expected: PASS。

- [ ] **Step 7: 运行全量 Ruff**

Run:

```bash
uv run ruff check .
```

Expected: `All checks passed!`

- [ ] **Step 8: 重建 CodeGraph 索引**

Run:

```bash
codegraph index --force
```

Expected: 索引成功完成，无 fatal error。

- [ ] **Step 9: 做最终残留扫描**

Run:

```bash
rg -n "channels\\.adapters\\.feishu|channels\\.adapters\\.dingtalk|channels\\.adapters\\.weixin_clawbot|channels\\.weixin_startup" deepclaw tests
```

Expected: 无输出。
