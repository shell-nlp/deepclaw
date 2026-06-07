# Web Backend 目录重构 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 `langchain_api/api`、`langchain_api/auth`、`langchain_api/channels`、`langchain_api/management` 中的 Web 相关代码重组到 `langchain_api/web_backend/`，形成扁平的按功能聚合结构，同时保持现有 HTTP 路径和行为不变。

**Architecture:** 新建 `langchain_api/web_backend/` 作为唯一 Web 应用壳，`auth`、`channels`、`skills`、`knowledge_bases`、`agent`、`rag` 都以功能目录聚合，`app.py` 和 `lifespan.py` 统一负责装配。根包下继续保留 `agent`、`rag`、`common`、`middleware`、`tools` 等核心能力层，避免让核心实现反向依赖 Web 层。

**Tech Stack:** Python 3.12、FastAPI、Pydantic、SQLModel、httpx、Elasticsearch、pytest、Ruff、CodeGraph

---

### Task 1: 建立 `web_backend` 骨架并准备迁移入口

**Files:**
- Create: `langchain_api/web_backend/__init__.py`
- Create: `langchain_api/web_backend/app.py`
- Create: `langchain_api/web_backend/lifespan.py`
- Create: `langchain_api/web_backend/common/__init__.py`
- Create: `langchain_api/web_backend/common/endpoints.py`
- Create: `langchain_api/web_backend/agent/__init__.py`
- Create: `langchain_api/web_backend/agent/router.py`
- Create: `langchain_api/web_backend/rag/__init__.py`
- Create: `langchain_api/web_backend/rag/router.py`
- Modify: `langchain_api/main.py`

- [ ] **Step 1: 先跑应用入口相关回归测试，确认当前基线可用**

Run: `uv run pytest tests/test_auth_bootstrap_startup.py tests/test_auth_context.py -q`
Expected: 现有启动与认证上下文测试通过，作为迁移前护栏

- [ ] **Step 2: 新建 `web_backend` 包和子包空文件**

```powershell
New-Item -ItemType Directory -Force langchain_api\web_backend\common
New-Item -ItemType Directory -Force langchain_api\web_backend\agent
New-Item -ItemType Directory -Force langchain_api\web_backend\rag
Set-Content langchain_api\web_backend\__init__.py '"""Web 应用层包。"""'
Set-Content langchain_api\web_backend\common\__init__.py '"""Web 通用组件。"""'
Set-Content langchain_api\web_backend\agent\__init__.py 'from .router import create_agent_router'
Set-Content langchain_api\web_backend\rag\__init__.py 'from .router import create_rag_router'
```

- [ ] **Step 3: 迁移公共 SSE 入口并修正依赖**

```python
from langchain_api.api.common.schemas.endpoints import (
    GeneralApiRequest,
    MultiModalQueryItem,
)
from langchain_api.web_backend.auth.dependencies import (
    CurrentActor,
    get_current_actor,
)
```

- [ ] **Step 4: 建立新的生命周期模块，承接 `main.py` 中的副作用初始化**

```python
@asynccontextmanager
async def app_lifespan(app: FastAPI):
    setup_observability()
    patch_langchain()
    get_auth_service().bootstrap_admin_if_needed()
    async with channel_lifespan():
        yield
```

- [ ] **Step 5: 建立新的 `web_backend/app.py` 装配入口**

```python
def create_app() -> FastAPI:
    app = FastAPI(lifespan=app_lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    checkpointer, store = init_agent_env()
    app.include_router(create_auth_router())
    app.include_router(create_agent_router(checkpointer, store))
    app.include_router(create_rag_router(checkpointer, store))
    app.include_router(create_channels_router())
    return app
```

- [ ] **Step 6: 让旧 `langchain_api/main.py` 暂时只保留薄入口，降低迁移期震荡**

```python
from langchain_api.web_backend.app import app, create_app


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=7869)
```

- [ ] **Step 7: 运行入口语法检查**

Run: `uv run python -m py_compile langchain_api/web_backend/app.py langchain_api/web_backend/lifespan.py langchain_api/main.py`
Expected: 退出码为 0，无语法错误

### Task 2: 迁移 `auth` 到 `web_backend/auth`

**Files:**
- Create: `langchain_api/web_backend/auth/__init__.py`
- Create: `langchain_api/web_backend/auth/router.py`
- Create: `langchain_api/web_backend/auth/schemas.py`
- Create: `langchain_api/web_backend/auth/service.py`
- Create: `langchain_api/web_backend/auth/store.py`
- Create: `langchain_api/web_backend/auth/models.py`
- Create: `langchain_api/web_backend/auth/security.py`
- Create: `langchain_api/web_backend/auth/dependencies.py`
- Modify: `langchain_api/web_backend/common/endpoints.py`
- Modify: `tests/test_auth_bootstrap_startup.py`
- Modify: `tests/test_auth_context.py`
- Modify: `tests/test_auth_permissions.py`
- Modify: `tests/test_auth_routes.py`
- Modify: `tests/test_auth_store.py`
- Delete: `langchain_api/auth/`
- Delete: `langchain_api/api/auth/`

- [ ] **Step 1: 先把现有 `auth` 模块整批移动到新目录，保持实现不变**

```powershell
New-Item -ItemType Directory -Force langchain_api\web_backend\auth
Move-Item langchain_api\auth\models.py langchain_api\web_backend\auth\models.py
Move-Item langchain_api\auth\store.py langchain_api\web_backend\auth\store.py
Move-Item langchain_api\auth\service.py langchain_api\web_backend\auth\service.py
Move-Item langchain_api\auth\security.py langchain_api\web_backend\auth\security.py
Move-Item langchain_api\auth\dependencies.py langchain_api\web_backend\auth\dependencies.py
Move-Item langchain_api\api\auth\api\routes.py langchain_api\web_backend\auth\router.py
```

- [ ] **Step 2: 合并认证 schema，去掉 `schemas/auth.py` 和 `schemas/users.py` 的分散拆分**

```python
class LoginRequest(BaseModel):
    email: str
    password: str


class AdminUpdateUserRoleRequest(BaseModel):
    user_id: str
    role: str
```

- [ ] **Step 3: 统一修正 `auth` 新目录内部导入**

```python
from langchain_api.web_backend.auth.models import (
    AccessToken,
    AuthenticatedActor,
    User,
)
from langchain_api.web_backend.auth.security import hash_token
```

- [ ] **Step 4: 让新 `router.py` 只依赖同目录的 `schemas/service/dependencies`**

```python
from langchain_api.web_backend.auth.dependencies import CurrentActor
from langchain_api.web_backend.auth.schemas import (
    AdminCreateUserRequest,
    AdminListUsersRequest,
    AdminResetUserPasswordRequest,
    AdminUpdateUserRoleRequest,
    AdminUpdateUserStatusRequest,
    LoginRequest,
    RegisterRequest,
)
from langchain_api.web_backend.auth.service import AuthService, get_auth_service
```

- [ ] **Step 5: 更新测试导入到新路径**

```python
from langchain_api.web_backend.auth.service import AuthService
from langchain_api.web_backend.auth.store import AuthStore
from langchain_api.web_backend.auth.dependencies import (
    CurrentActor,
    get_current_actor,
)
from langchain_api.web_backend.auth.router import create_auth_router
```

- [ ] **Step 6: 跑认证测试，确保目录迁移不改变行为**

Run: `uv run pytest tests/test_auth_bootstrap_startup.py tests/test_auth_context.py tests/test_auth_permissions.py tests/test_auth_routes.py tests/test_auth_store.py -q`
Expected: 认证相关测试全部通过

- [ ] **Step 7: 删除已空的旧 `auth` 目录和旧 API 目录**

```powershell
Remove-Item -Recurse -Force langchain_api\auth
Remove-Item -Recurse -Force langchain_api\api\auth
```

### Task 3: 迁移 `channels` 到 `web_backend/channels`

**Files:**
- Create: `langchain_api/web_backend/channels/__init__.py`
- Create: `langchain_api/web_backend/channels/router.py`
- Create: `langchain_api/web_backend/channels/schemas.py`
- Create: `langchain_api/web_backend/channels/service.py`
- Create: `langchain_api/web_backend/channels/store.py`
- Create: `langchain_api/web_backend/channels/models.py`
- Create: `langchain_api/web_backend/channels/config.py`
- Create: `langchain_api/web_backend/channels/dispatcher.py`
- Create: `langchain_api/web_backend/channels/lifespan.py`
- Create: `langchain_api/web_backend/channels/weixin_startup.py`
- Create: `langchain_api/web_backend/channels/agent_client.py`
- Create: `langchain_api/web_backend/channels/adapters/*`
- Modify: `langchain_api/web_backend/lifespan.py`
- Modify: `tests/test_channels_agent_client.py`
- Modify: `tests/test_channels_config.py`
- Modify: `tests/test_channels_dispatcher.py`
- Modify: `tests/test_channels_lifespan.py`
- Modify: `tests/test_channels_router.py`
- Modify: `tests/test_channels_service.py`
- Modify: `tests/test_channels_store.py`
- Modify: `tests/test_channels_weixin_clawbot.py`
- Modify: `tests/test_channels_weixin_startup.py`
- Delete: `langchain_api/channels/`
- Delete: `langchain_api/api/channels/`

- [ ] **Step 1: 整批迁移 `channels` 目录，先保留文件边界，再调整导入**

```powershell
New-Item -ItemType Directory -Force langchain_api\web_backend\channels\adapters
Move-Item langchain_api\channels\agent_client.py langchain_api\web_backend\channels\agent_client.py
Move-Item langchain_api\channels\config.py langchain_api\web_backend\channels\config.py
Move-Item langchain_api\channels\dispatcher.py langchain_api\web_backend\channels\dispatcher.py
Move-Item langchain_api\channels\lifespan.py langchain_api\web_backend\channels\lifespan.py
Move-Item langchain_api\channels\models.py langchain_api\web_backend\channels\models.py
Move-Item langchain_api\channels\service.py langchain_api\web_backend\channels\service.py
Move-Item langchain_api\channels\store.py langchain_api\web_backend\channels\store.py
Move-Item langchain_api\channels\weixin_startup.py langchain_api\web_backend\channels\weixin_startup.py
Move-Item langchain_api\channels\adapters\* langchain_api\web_backend\channels\adapters\
Move-Item langchain_api\api\channels\api\routes.py langchain_api\web_backend\channels\router.py
```

- [ ] **Step 2: 合并微信渠道请求模型到单个 `schemas.py`**

```python
class WeixinClawBotPollRequest(BaseModel):
    bot_token: str
    get_updates_buf: str | None = None


class WeixinClawBotBoundUserDeleteResponse(BaseModel):
    user_id: str
    deleted: bool
```

- [ ] **Step 3: 批量修正 `channels` 内部相互引用**

```python
from langchain_api.web_backend.channels.adapters.base import ChannelAdapter
from langchain_api.web_backend.channels.agent_client import AgentClient
from langchain_api.web_backend.channels.config import weixin_clawbot_settings
from langchain_api.web_backend.channels.store import ChannelStore, get_channel_store
```

- [ ] **Step 4: 修正 `web_backend/lifespan.py` 对渠道生命周期的导入**

```python
from langchain_api.web_backend.channels.lifespan import channel_lifespan
```

- [ ] **Step 5: 更新渠道测试导入到新路径**

```python
from langchain_api.web_backend.channels.agent_client import AgentClient
from langchain_api.web_backend.channels.models import AgentEvent, ChannelMessage
from langchain_api.web_backend.channels.router import create_channels_router
from langchain_api.web_backend.channels.store import ChannelStore
```

- [ ] **Step 6: 跑渠道测试，确认复杂导入链稳定**

Run: `uv run pytest tests/test_channels_agent_client.py tests/test_channels_config.py tests/test_channels_dispatcher.py tests/test_channels_lifespan.py tests/test_channels_router.py tests/test_channels_service.py tests/test_channels_store.py tests/test_channels_weixin_clawbot.py tests/test_channels_weixin_startup.py -q`
Expected: 渠道相关测试全部通过

- [ ] **Step 7: 删除旧 `channels` 目录和旧 API 目录**

```powershell
Remove-Item -Recurse -Force langchain_api\channels
Remove-Item -Recurse -Force langchain_api\api\channels
```

### Task 4: 迁移 `skills`、`knowledge_bases`、`agent`、`rag` 路由入口

**Files:**
- Create: `langchain_api/web_backend/skills/__init__.py`
- Create: `langchain_api/web_backend/skills/router.py`
- Create: `langchain_api/web_backend/skills/schemas.py`
- Create: `langchain_api/web_backend/skills/service.py`
- Create: `langchain_api/web_backend/knowledge_bases/__init__.py`
- Create: `langchain_api/web_backend/knowledge_bases/router.py`
- Create: `langchain_api/web_backend/knowledge_bases/schemas.py`
- Create: `langchain_api/web_backend/knowledge_bases/service.py`
- Create: `langchain_api/web_backend/agent/router.py`
- Create: `langchain_api/web_backend/rag/router.py`
- Modify: `tests/test_auth_permissions.py`
- Delete: `langchain_api/management/`
- Delete: `langchain_api/api/agent/`
- Delete: `langchain_api/api/rag/`
- Delete: `langchain_api/api/common/`

- [ ] **Step 1: 迁移技能管理实现和路由**

```powershell
New-Item -ItemType Directory -Force langchain_api\web_backend\skills
Move-Item langchain_api\management\skill_manager.py langchain_api\web_backend\skills\service.py
Move-Item langchain_api\api\agent\api\skills.py langchain_api\web_backend\skills\router.py
Move-Item langchain_api\api\agent\schemas\skills.py langchain_api\web_backend\skills\schemas.py
```

- [ ] **Step 2: 迁移知识库管理实现和路由**

```powershell
New-Item -ItemType Directory -Force langchain_api\web_backend\knowledge_bases
Move-Item langchain_api\management\knowledge_base_manager.py langchain_api\web_backend\knowledge_bases\service.py
Move-Item langchain_api\api\rag\api\knowledge_bases.py langchain_api\web_backend\knowledge_bases\router.py
Move-Item langchain_api\api\rag\schemas\knowledge_bases.py langchain_api\web_backend\knowledge_bases\schemas.py
```

- [ ] **Step 3: 建立新的 `agent` 和 `rag` HTTP 路由入口**

```python
from langchain_api.agent.agent import Agent
from langchain_api.agent.context import AgentContext
from langchain_api.web_backend.common.endpoints import add_general_api_endpoint
from langchain_api.web_backend.skills.router import add_skill_management_routes
```

```python
from langchain_api.rag.agent import create_rag_agent
from langchain_api.rag.context import AgentContext
from langchain_api.web_backend.common.endpoints import add_general_api_endpoint
from langchain_api.web_backend.knowledge_bases.router import (
    add_knowledge_base_management_routes,
)
```

- [ ] **Step 4: 修正 `skills`、`knowledge_bases` 新模块内部导入**

```python
from langchain_api.web_backend.auth.dependencies import get_current_actor
from langchain_api.web_backend.skills.schemas import (
    SkillDeleteRequest,
    SkillListRequest,
)
from langchain_api.web_backend.knowledge_bases.schemas import (
    KnowledgeBaseListRequest,
    UpdateKnowledgeBaseRequest,
)
```

- [ ] **Step 5: 更新权限相关测试导入**

```python
from langchain_api.web_backend.skills.router import add_skill_management_routes
from langchain_api.web_backend.knowledge_bases.router import (
    add_knowledge_base_management_routes,
)
```

- [ ] **Step 6: 跑管理与路由装配相关测试**

Run: `uv run pytest tests/test_auth_permissions.py tests/test_auth_context.py -q`
Expected: 技能管理、知识库管理和通用上下文权限测试通过

- [ ] **Step 7: 删除旧 `management` 与旧 API 子树**

```powershell
Remove-Item -Recurse -Force langchain_api\management
Remove-Item -Recurse -Force langchain_api\api\agent
Remove-Item -Recurse -Force langchain_api\api\rag
Remove-Item -Recurse -Force langchain_api\api\common
```

### Task 5: 收口应用入口、测试引用和文档

**Files:**
- Modify: `langchain_api/web_backend/app.py`
- Modify: `langchain_api/main.py`
- Modify: `tests/*.py`
- Modify: `AGENTS.md`
- Modify: `README.md`
- Delete: `langchain_api/api/__init__.py`
- Delete: `langchain_api/api/`

- [ ] **Step 1: 在 `web_backend/app.py` 中统一挂载所有新 router**

```python
app.include_router(create_auth_router())
app.include_router(create_agent_router(checkpointer, store))
app.include_router(create_rag_router(checkpointer, store))
app.include_router(create_channels_router())
```

```python
app.include_router(create_skills_router())
app.include_router(create_knowledge_bases_router())
```

- [ ] **Step 2: 清理测试中残留的旧导入路径**

```powershell
rg -n "langchain_api\\.(api|auth|channels|management)" tests langchain_api
```

Expected: 只剩下应当保留的 `langchain_api.agent`、`langchain_api.rag`、`langchain_api.common` 等核心能力导入

- [ ] **Step 3: 更新 `AGENTS.md` 中的目录结构和启动说明**

```markdown
- `langchain_api/web_backend/app.py`
  FastAPI 唯一装配入口，负责注册 auth、agent、rag、channels、skills、knowledge_bases 路由。
- `langchain_api/web_backend/auth/`
  认证相关路由、模型、依赖、存储与服务。
- `langchain_api/web_backend/channels/`
  渠道相关路由、运行时存储、适配器和生命周期管理。
```

- [ ] **Step 4: 更新 `README.md` 启动命令到新入口**

```bash
uv run uvicorn langchain_api.web_backend.app:app --reload --host 0.0.0.0 --port 7869
```

- [ ] **Step 5: 删除空的旧 `api` 根目录**

```powershell
Remove-Item -Recurse -Force langchain_api\api
```

### Task 6: 全量验证并更新 CodeGraph

**Files:**
- Test: `langchain_api/web_backend/**/*.py`
- Test: `tests/*.py`
- Index: `.codegraph/`

- [ ] **Step 1: 对全部修改过的 Python 文件运行语法检查**

Run: `uv run python -m py_compile langchain_api/main.py langchain_api/web_backend/app.py langchain_api/web_backend/lifespan.py langchain_api/web_backend/common/endpoints.py langchain_api/web_backend/agent/router.py langchain_api/web_backend/rag/router.py langchain_api/web_backend/auth/*.py langchain_api/web_backend/channels/*.py langchain_api/web_backend/channels/adapters/*.py langchain_api/web_backend/skills/*.py langchain_api/web_backend/knowledge_bases/*.py`
Expected: 退出码为 0，无语法错误

- [ ] **Step 2: 运行全仓 Ruff**

Run: `uv run ruff check .`
Expected: 退出码为 0，无新增 lint 问题

- [ ] **Step 3: 运行全量 pytest**

Run: `uv run pytest tests -q`
Expected: 所有现有测试通过，确认目录重构没有引入行为回归

- [ ] **Step 4: 更新 CodeGraph 索引**

Run: `codegraph index --force`
Expected: 索引成功完成，后续结构查询反映最新目录

- [ ] **Step 5: 提交重构**

```bash
git add langchain_api/web_backend langchain_api/main.py tests AGENTS.md README.md docs/superpowers/specs/2026-06-07-web-backend-refactor-design.md docs/superpowers/plans/2026-06-07-web-backend-refactor-implementation.md
git commit -m "refactor: regroup web backend modules"
```
