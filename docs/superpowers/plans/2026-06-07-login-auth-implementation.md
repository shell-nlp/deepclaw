# 登录与账号管理 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为仓库补齐游客态、邮箱密码注册登录、Bearer Token 鉴权和管理员用户管理，并把知识库/技能等写操作限制为登录后可用。

**Architecture:** 后端新增 `langchain_api/auth` 子系统，使用本地 SQLite 保存用户和访问令牌摘要；API 层统一解析 `CurrentActor`，再把真实 `user_id` 注入现有业务逻辑。前端保留现有工作台结构，默认游客直达工作台，只在点击右上角头像时进入登录/注册流程，并在管理页中对游客展示只读禁用态和友好提示。

**Tech Stack:** FastAPI, SQLModel, Pydantic, Next.js 15, React 19, TypeScript, Node `node:test`

---

### Task 1: 建立认证模型、存储和安全工具

**Files:**
- Create: `langchain_api/auth/models.py`
- Create: `langchain_api/auth/security.py`
- Create: `langchain_api/auth/store.py`
- Create: `langchain_api/auth/service.py`
- Create: `langchain_api/auth/__init__.py`
- Modify: `langchain_api/settings.py`
- Test: `tests/test_auth_store.py`

- [ ] **Step 1: 先写失败测试，锁定认证基础行为**

```python
from langchain_api.auth.service import AuthService
from langchain_api.auth.store import AuthStore


def build_service() -> AuthService:
    return AuthService(
        store=AuthStore("sqlite:///:memory:"),
        admin_email="admin@example.com",
        admin_password="admin-pass-123",
        token_expire_days=30,
    )


def test_bootstrap_admin_and_issue_token():
    service = build_service()

    admin = service.bootstrap_admin_if_needed()
    issued = service.login(email="admin@example.com", password="admin-pass-123")
    actor = service.authenticate_token(issued.token)

    assert admin is not None
    assert admin.role == "admin"
    assert actor.user.email == "admin@example.com"


def test_register_rejects_duplicate_email():
    service = build_service()

    service.register(email="user@example.com", password="secret-123")

    try:
        service.register(email="user@example.com", password="secret-456")
    except ValueError as exc:
        assert str(exc) == "该邮箱已注册，请直接登录。"
    else:
        raise AssertionError("expected duplicate email error")
```

- [ ] **Step 2: 运行测试，确认当前缺少认证模块而失败**

Run: `uv run pytest tests/test_auth_store.py -q`

Expected: `ModuleNotFoundError` 或 `ImportError`，指向 `langchain_api.auth`

- [ ] **Step 3: 写最小生产代码，覆盖用户表、token 表、哈希和服务**

```python
# langchain_api/auth/models.py
from datetime import UTC, datetime

from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class AuthUser(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    user_id: str = Field(index=True, unique=True)
    email: str = Field(index=True, unique=True)
    password_hash: str
    role: str = Field(default="user")
    is_active: bool = True
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class AccessTokenRecord(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    user_id: str = Field(index=True)
    token_hash: str = Field(index=True, unique=True)
    expires_at: datetime
    last_used_at: datetime | None = None
    created_at: datetime = Field(default_factory=utc_now)
```

```python
# langchain_api/auth/security.py
import hashlib
import secrets


def hash_password(password: str, salt: str | None = None) -> str:
    actual_salt = salt or secrets.token_hex(16)
    digest = hashlib.scrypt(
        password.encode("utf-8"),
        salt=actual_salt.encode("utf-8"),
        n=16384,
        r=8,
        p=1,
    )
    return f"{actual_salt}${digest.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    salt, _ = encoded.split("$", 1)
    return hash_password(password, salt=salt) == encoded


def generate_access_token() -> str:
    return f"la_{secrets.token_urlsafe(32)}"


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
```

```python
# langchain_api/auth/service.py
class AuthService:
    def register(self, *, email: str, password: str):
        normalized_email = email.strip().lower()
        if self.store.get_user_by_email(normalized_email):
            raise ValueError("该邮箱已注册，请直接登录。")
        return self.store.create_user(
            email=normalized_email,
            password_hash=hash_password(password),
            role="user",
        )

    def login(self, *, email: str, password: str):
        normalized_email = email.strip().lower()
        user = self.store.get_user_by_email(normalized_email)
        if user is None or not verify_password(password, user.password_hash):
            raise ValueError("邮箱或密码错误。")
        if not user.is_active:
            raise ValueError("当前账号已被禁用，请联系管理员。")
        raw_token = generate_access_token()
        return self.store.issue_access_token(
            user=user,
            raw_token=raw_token,
            expire_days=self.token_expire_days,
        )

    def authenticate_token(self, token: str):
        return self.store.get_actor_by_token(token)

    def bootstrap_admin_if_needed(self):
        if self.store.has_admin_user():
            return None
        if not self.admin_email or not self.admin_password:
            return None
        return self.store.create_user(
            email=self.admin_email.strip().lower(),
            password_hash=hash_password(self.admin_password),
            role="admin",
        )
```

- [ ] **Step 4: 增加配置项并通过后端测试**

```python
# langchain_api/settings.py
AUTH_ADMIN_EMAIL: str | None = None
AUTH_ADMIN_PASSWORD: str | None = None
AUTH_TOKEN_EXPIRE_DAYS: int = 30
```

Run: `uv run pytest tests/test_auth_store.py -q`

Expected: `2 passed`

- [ ] **Step 5: 运行语法检查**

Run: `uv run python -m py_compile langchain_api/auth/models.py langchain_api/auth/security.py langchain_api/auth/store.py langchain_api/auth/service.py langchain_api/settings.py`

Expected: no output

### Task 2: 暴露认证路由和管理员用户管理路由

**Files:**
- Create: `langchain_api/auth/dependencies.py`
- Create: `langchain_api/api/auth/api/routes.py`
- Create: `langchain_api/api/auth/api/__init__.py`
- Create: `langchain_api/api/auth/schemas/auth.py`
- Create: `langchain_api/api/auth/schemas/users.py`
- Create: `langchain_api/api/auth/schemas/__init__.py`
- Create: `langchain_api/api/auth/__init__.py`
- Modify: `langchain_api/main.py`
- Test: `tests/test_auth_routes.py`

- [ ] **Step 1: 写失败测试，锁定注册、登录、游客 `me` 和管理员创建用户**

```python
from fastapi import FastAPI
from fastapi.testclient import TestClient

from langchain_api.api.auth.api.routes import create_auth_router
from langchain_api.auth.service import AuthService
from langchain_api.auth.store import AuthStore


def build_client() -> TestClient:
    store = AuthStore("sqlite:///:memory:")
    service = AuthService(
        store=store,
        admin_email="admin@example.com",
        admin_password="admin-pass-123",
        token_expire_days=30,
    )
    service.bootstrap_admin_if_needed()
    app = FastAPI()
    app.include_router(create_auth_router(service=service))
    return TestClient(app)


def test_guest_me_and_register_login_flow():
    client = build_client()

    guest = client.get("/api/auth/me")
    register = client.post(
        "/api/auth/register",
        json={"email": "user@example.com", "password": "secret-123"},
    )
    login = client.post(
        "/api/auth/login",
        json={"email": "user@example.com", "password": "secret-123"},
    )

    assert guest.status_code == 200
    assert guest.json()["is_guest"] is True
    assert register.status_code == 200
    assert login.status_code == 200
    assert login.json()["user"]["role"] == "user"


def test_admin_can_create_user():
    client = build_client()
    login = client.post(
        "/api/auth/login",
        json={"email": "admin@example.com", "password": "admin-pass-123"},
    )
    token = login.json()["token"]

    response = client.post(
        "/api/auth/users/create",
        json={"email": "created@example.com", "password": "created-pass-123", "role": "user"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["user"]["email"] == "created@example.com"
```

- [ ] **Step 2: 运行测试，确认当前认证路由不存在而失败**

Run: `uv run pytest tests/test_auth_routes.py -q`

Expected: `ModuleNotFoundError`，指向 `langchain_api.api.auth`

- [ ] **Step 3: 写依赖和路由，补齐游客/登录/管理员三态**

```python
# langchain_api/auth/dependencies.py
from fastapi import Depends, Header, HTTPException
from pydantic import BaseModel


class CurrentActor(BaseModel):
    is_guest: bool
    user_id: str | None
    email: str | None
    role: str


def get_current_actor(
    authorization: str | None = Header(default=None),
    service: AuthService = Depends(get_auth_service),
) -> CurrentActor:
    if not authorization:
        return CurrentActor(is_guest=True, user_id=None, email=None, role="guest")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=401, detail="登录状态已失效，请重新登录。")
    actor = service.authenticate_token(token)
    return CurrentActor(
        is_guest=False,
        user_id=actor.user.user_id,
        email=actor.user.email,
        role=actor.user.role,
    )


def require_authenticated_actor(
    actor: CurrentActor = Depends(get_current_actor),
) -> CurrentActor:
    if actor.is_guest:
        raise HTTPException(status_code=403, detail="请先登录后再使用该功能。")
    return actor


def require_admin_actor(
    actor: CurrentActor = Depends(require_authenticated_actor),
) -> CurrentActor:
    if actor.role != "admin":
        raise HTTPException(status_code=403, detail="只有管理员可以执行该操作。")
    return actor
```

```python
# langchain_api/api/auth/api/routes.py
from fastapi import APIRouter, Depends, Header


def create_auth_router(service=None) -> APIRouter:
    router = APIRouter(prefix="/api/auth", tags=["auth"])
    auth_service = service or get_auth_service()

    @router.post("/register")
    def register(request: RegisterRequest):
        user = auth_service.register(email=request.email, password=request.password)
        issued = auth_service.login(email=request.email, password=request.password)
        return {
            "token": issued.token,
            "user": {
                "email": user.email,
                "role": user.role,
                "is_active": user.is_active,
                "user_id": user.user_id,
            },
        }

    @router.post("/login")
    def login(request: LoginRequest):
        issued = auth_service.login(email=request.email, password=request.password)
        return {
            "token": issued.token,
            "user": {
                "email": issued.user.email,
                "role": issued.user.role,
                "is_active": issued.user.is_active,
                "user_id": issued.user.user_id,
            },
        }

    @router.post("/logout")
    def logout(
        actor=Depends(require_authenticated_actor),
        authorization: str | None = Header(default=None),
    ):
        token = (authorization or "").split(" ", 1)[1]
        auth_service.revoke_token(token)
        return {"ok": True}

    @router.get("/me")
    def me(actor=Depends(get_current_actor)):
        return actor.model_dump()

    @router.post("/users/create")
    def create_user(
        request: AdminCreateUserRequest,
        actor=Depends(require_admin_actor),
    ):
        user = auth_service.create_user_as_admin(
            email=request.email,
            password=request.password,
            role=request.role,
        )
        return {
            "user": {
                "email": user.email,
                "role": user.role,
                "is_active": user.is_active,
                "user_id": user.user_id,
            }
        }

    return router
```

```python
# langchain_api/main.py
from langchain_api.api.auth import create_auth_router
from langchain_api.api.agent import create_agent_router
from langchain_api.api.channels import create_channels_router
from langchain_api.api.rag import create_rag_router

checkpointer, store = init_agent_env()
app.include_router(create_auth_router())
app.include_router(create_agent_router(checkpointer, store))
app.include_router(create_rag_router(checkpointer, store))
app.include_router(create_channels_router())
```

- [ ] **Step 4: 运行测试并做语法校验**

Run: `uv run pytest tests/test_auth_routes.py -q`

Expected: `2 passed`

Run: `uv run python -m py_compile langchain_api/auth/dependencies.py langchain_api/api/auth/api/routes.py langchain_api/api/auth/schemas/auth.py langchain_api/api/auth/schemas/users.py langchain_api/main.py`

Expected: no output

### Task 3: 给知识库、技能和聊天入口接入权限

**Files:**
- Modify: `langchain_api/api/common/api/endpoints.py`
- Modify: `langchain_api/api/agent/api/skills.py`
- Modify: `langchain_api/api/rag/api/knowledge_bases.py`
- Modify: `langchain_api/api/agent/api/routes.py`
- Modify: `langchain_api/api/rag/api/routes.py`
- Test: `tests/test_auth_permissions.py`

- [ ] **Step 1: 写失败测试，固定游客禁写行为**

```python
from fastapi import FastAPI
from fastapi.testclient import TestClient

from langchain_api.api.agent.api.routes import create_agent_router
from langchain_api.api.auth.api.routes import create_auth_router
from langchain_api.api.rag.api.routes import create_rag_router
from langchain_api.auth.service import AuthService
from langchain_api.auth.store import AuthStore


def test_guest_cannot_upload_skill_or_create_kb():
    app = FastAPI()
    store = AuthStore("sqlite:///:memory:")
    service = AuthService(
        store=store,
        admin_email=None,
        admin_password=None,
        token_expire_days=30,
    )
    app.include_router(create_auth_router(service=service))
    app.include_router(create_agent_router())
    app.include_router(create_rag_router())
    client = TestClient(app, raise_server_exceptions=False)

    skill = client.post(
        "/api/agent/skills/upload",
        files={"file": ("skill.zip", b"fake", "application/zip")},
    )
    kb = client.post(
        "/api/rag/knowledge-bases/create",
        json={"user_id": "guest", "name": "demo", "description": ""},
    )

    assert skill.status_code == 403
    assert skill.json()["detail"] == "登录后可上传技能。"
    assert kb.status_code == 403
    assert kb.json()["detail"] == "登录后可创建知识库。"
```

- [ ] **Step 2: 运行测试，确认当前接口尚未鉴权而失败**

Run: `uv run pytest tests/test_auth_permissions.py -q`

Expected: 断言失败，因为当前返回不是 `403`

- [ ] **Step 3: 扩展通用 SSE 端点，统一注入真实 user_id**

```python
# langchain_api/api/common/api/endpoints.py
def add_general_api_endpoint(
    app: FastAPI | APIRouter,
    agent: CompiledStateGraph,
    path: str = "/api/general_api",
    context: type[BaseModel] | None = None,
    name: str | None = None,
    tags: list[str] | None = None,
    actor_resolver=None,
    allow_guest: bool = False,
):
    actor_dependency = Depends(actor_resolver) if actor_resolver else None

    @app.post(path, response_model=StreamResponse, name=route_name, tags=tags)
    async def general_api(request: Request, actor=actor_dependency):
        if actor and not allow_guest and actor.is_guest:
            raise HTTPException(status_code=403, detail="请先登录后再使用该功能。")

        if actor and actor.user_id:
            request = request.model_copy(update={"user_id": actor.user_id})
```

```python
# langchain_api/api/agent/api/routes.py
add_general_api_endpoint(
    app=general_api_router,
    agent=agent,
    path="/general_api",
    context=AgentContext,
    name="agent_general_api",
    tags=["agent-chat"],
    actor_resolver=get_current_actor,
    allow_guest=True,
)
```

- [ ] **Step 4: 在技能和知识库接口里收口游客写权限**

```python
# langchain_api/api/agent/api/skills.py
async def upload_skill(
    file: UploadFile = File(..., description="Skill zip package"),
    actor=Depends(require_authenticated_actor),
):
    if actor.role not in {"user", "admin"}:
        raise HTTPException(status_code=403, detail="登录后可上传技能。")
```

```python
# langchain_api/api/rag/api/knowledge_bases.py
def _resolve_user_id(actor, request_user_id: str | None = None) -> str:
    if actor.is_guest:
        raise HTTPException(status_code=403, detail="登录后可创建知识库。")
    return actor.user_id


def create_knowledge_base(request: CreateKnowledgeBaseRequest, actor=Depends(require_authenticated_actor)):
    return knowledge_base_manager.create_knowledge_base(
        user_id=_resolve_user_id(actor, request.user_id),
        name=request.name,
        description=request.description,
    )
```

- [ ] **Step 5: 运行权限测试和语法检查**

Run: `uv run pytest tests/test_auth_permissions.py -q`

Expected: `1 passed`

Run: `uv run python -m py_compile langchain_api/api/common/api/endpoints.py langchain_api/api/agent/api/skills.py langchain_api/api/rag/api/knowledge_bases.py langchain_api/api/agent/api/routes.py langchain_api/api/rag/api/routes.py`

Expected: no output

### Task 4: 接入前端认证状态、token 存储和鉴权请求工具

**Files:**
- Create: `frontend/components/chat-interface/auth.ts`
- Modify: `frontend/components/chat-interface/constants.ts`
- Modify: `frontend/components/chat-interface/types.ts`
- Modify: `frontend/components/chat-interface/utils.ts`
- Modify: `frontend/tests/chat-runtime.test.mjs`
- Create: `frontend/tests/auth-utils.test.mjs`

- [ ] **Step 1: 先写失败测试，固定游客默认态和 Bearer 头**

```javascript
import test from 'node:test'
import assert from 'node:assert/strict'

import * as authPkg from '../components/chat-interface/auth.ts'

test('guest session is used when no token exists', () => {
  assert.deepEqual(authPkg.getStoredAuthState(), {
    token: null,
    actor: { isGuest: true, role: 'guest', email: null, userId: 'guest' },
  })
})

test('buildAuthHeaders attaches bearer token', () => {
  assert.deepEqual(authPkg.buildAuthHeaders('la_demo'), {
    Authorization: 'Bearer la_demo',
  })
})
```

- [ ] **Step 2: 运行测试，确认当前前端认证工具不存在而失败**

Run: `node --test frontend/tests/auth-utils.test.mjs`

Expected: `ERR_MODULE_NOT_FOUND`

- [ ] **Step 3: 写认证状态工具和鉴权请求包装**

```typescript
// frontend/components/chat-interface/auth.ts
export interface FrontendActor {
  isGuest: boolean
  role: 'guest' | 'user' | 'admin'
  email: string | null
  userId: string
}

export function getStoredAuthState() {
  return {
    token: null,
    actor: { isGuest: true, role: 'guest', email: null, userId: 'guest' as const },
  }
}

export function buildAuthHeaders(token: string | null): Record<string, string> {
  return token ? { Authorization: `Bearer ${token}` } : {}
}
```

```typescript
// frontend/components/chat-interface/utils.ts
export function withAuthHeaders(
  init: RequestInit | undefined,
  token: string | null
): RequestInit {
  return {
    ...init,
    headers: {
      ...buildAuthHeaders(token),
      ...(init?.headers ?? {}),
    },
  }
}

export async function fetchJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init)
  if (response.status === 401) {
    localStorage.removeItem('auth_token')
  }
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`)
  }
  return response.json() as Promise<T>
}
```

- [ ] **Step 4: 补认证常量和类型**

```typescript
// frontend/components/chat-interface/constants.ts
export const AUTH_LOGIN_API_PATH = '/api/auth/login'
export const AUTH_REGISTER_API_PATH = '/api/auth/register'
export const AUTH_LOGOUT_API_PATH = '/api/auth/logout'
export const AUTH_ME_API_PATH = '/api/auth/me'
export const AUTH_USERS_CREATE_API_PATH = '/api/auth/users/create'
```

```typescript
// frontend/components/chat-interface/types.ts
export interface AuthActor {
  is_guest: boolean
  role: 'guest' | 'user' | 'admin'
  email?: string | null
  user_id?: string | null
}
```

- [ ] **Step 5: 跑前端测试和类型检查**

Run: `node --test frontend/tests/chat-runtime.test.mjs frontend/tests/auth-utils.test.mjs`

Expected: all tests pass

Run: `cd frontend && pnpm lint`

Expected: no type errors

### Task 5: 改造工作台 UI，加入游客态、登录页和真实账号管理页

**Files:**
- Modify: `frontend/components/ChatInterface.tsx`
- Modify: `frontend/components/ChatInterface.module.css`
- Modify: `frontend/components/chat-interface/KnowledgeManagementView.tsx`
- Modify: `frontend/components/chat-interface/constants.ts`
- Create: `frontend/components/chat-interface/AuthPanel.tsx`
- Create: `frontend/components/chat-interface/UserManagementView.tsx`
- Create: `frontend/components/chat-interface/auth-ui.ts`
- Create: `frontend/tests/auth-ui.test.mjs`

- [ ] **Step 1: 先写失败测试，锁定游客禁用态和管理员视图分流**

```javascript
import test from 'node:test'
import assert from 'node:assert/strict'

import * as authUiPkg from '../components/chat-interface/auth-ui.ts'

test('guest permissions disable skill and knowledge uploads', () => {
  assert.deepEqual(authUiPkg.getGuestFeatureFlags(), {
    canUploadSkill: false,
    canUploadKnowledge: false,
    canCreateKnowledgeBase: false,
    canUseMcpManagement: false,
    canUseChannelManagement: false,
  })
})

test('admin account page shows user management tools', () => {
  assert.equal(
    authUiPkg.getAccountViewMode({ isGuest: false, role: 'admin' }),
    'admin'
  )
})
```

- [ ] **Step 2: 运行测试，确认当前 UI 辅助模块不存在而失败**

Run: `node --test frontend/tests/auth-ui.test.mjs`

Expected: `ERR_MODULE_NOT_FOUND`

- [ ] **Step 3: 在 ChatInterface 里加入头像入口、登录面板和游客状态**

```tsx
// frontend/components/ChatInterface.tsx
const [authToken, setAuthToken] = useState<string | null>(null)
const [actor, setActor] = useState<AuthActor>({ is_guest: true, role: 'guest' })
const [showAuthPanel, setShowAuthPanel] = useState(false)

const isGuest = actor.is_guest

<header className={styles.header}>
  <div className={styles.headerContent}>
    <div className={styles.logoArea}>
      <span className={styles.logoIcon}>AI</span>
      <h1 className={styles.title}>AI Agent Chat</h1>
    </div>
    <button
      className={styles.accountButton}
      onClick={() => setShowAuthPanel(true)}
    >
      {isGuest ? '游客 / 登录' : actor.email}
    </button>
  </div>
</header>
```

```tsx
// frontend/components/chat-interface/AuthPanel.tsx
export function AuthPanel({ mode, onLogin, onRegister, onClose }: AuthPanelProps) {
  return (
    <div className={styles.authOverlay}>
      <div className={styles.authCard}>
        <h2>{mode === 'login' ? '登录账号' : '注册账号'}</h2>
        <input type="email" />
        <input type="password" />
        {mode === 'register' ? <input type="password" /> : null}
        <button onClick={mode === 'login' ? onLogin : onRegister}>
          {mode === 'login' ? '登录' : '注册'}
        </button>
        <button onClick={onClose}>返回工作台</button>
      </div>
    </div>
  )
}
```

- [ ] **Step 4: 把旧“用户管理”替换成真实账号管理页，并给游客显示友好禁用态**

```tsx
// frontend/components/chat-interface/KnowledgeManagementView.tsx
if (knowledgePage === 'users') {
  return (
    <UserManagementView
      actor={actor}
      users={users}
      onLoginClick={onOpenAuthPanel}
      onCreateUser={handleCreateUser}
      onToggleUserStatus={handleToggleUserStatus}
      onResetPassword={handleResetPassword}
    />
  )
}
```

```tsx
// frontend/components/chat-interface/UserManagementView.tsx
if (actor.is_guest) {
  return <div className={styles.managementEmpty}>登录后可管理账号。</div>
}

if (actor.role !== 'admin') {
  return (
    <div className={styles.managementMetaPanel}>
      当前账号角色：普通用户
    </div>
  )
}
```

```tsx
// guest disabled buttons
<button
  disabled={isGuest}
  title={isGuest ? '登录后可上传知识文件' : undefined}
>
  上传知识文件
</button>
```

- [ ] **Step 5: 跑前端测试、类型检查和构建**

Run: `node --test frontend/tests/chat-runtime.test.mjs frontend/tests/auth-utils.test.mjs frontend/tests/auth-ui.test.mjs`

Expected: all tests pass

Run: `cd frontend && pnpm lint && pnpm build`

Expected: lint and build succeed

### Task 6: 收尾验证、文档同步和索引刷新

**Files:**
- Modify: `AGENTS.md`
- Modify: `docs/superpowers/specs/2026-06-07-login-auth-design.md`
- Test: `tests/test_auth_store.py`
- Test: `tests/test_auth_routes.py`
- Test: `tests/test_auth_permissions.py`

- [ ] **Step 1: 核对协作约束和设计文档**

```md
- 未经用户明确要求，不要执行 `git add`、`git commit`、`git amend` 等 Git 提交类操作。
```

如果实现时合并了计划中的文件，立刻同步更新设计文档里的 `模块划分` 和 `认证接口设计` 两节，保证文档反映真实代码。

- [ ] **Step 2: 跑 Python 侧完整最小验证**

Run: `uv run pytest tests/test_auth_store.py tests/test_auth_routes.py tests/test_auth_permissions.py tests/test_channels_router.py -q`

Expected: all tests pass

Run: `uv run ruff check .`

Expected: no lint errors

- [ ] **Step 3: 刷新前端验证和 CodeGraph 索引**

Run: `cd frontend && pnpm lint && pnpm build`

Expected: lint and build succeed

Run: `codegraph index --force`

Expected: index refresh completes successfully

- [ ] **Step 4: 记录剩余风险**

```text
1. 游客是否允许查看知识库列表，是当前产品策略的一部分；本计划按既定规格保留可读。
2. Bearer Token 当前保存在 localStorage，后续如需更高安全等级，可改为 HttpOnly Cookie。
3. 技能管理当前按“登录用户可管理”实现；如果后续改成“仅管理员可管理”，需要补后端权限规则和前端按钮权限。
```
