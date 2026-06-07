# Channel Permission Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复渠道管理权限漏洞，让游客只管理公共游客账号下的数据、普通用户只管理自己的数据、管理员可以查看和删除全部数据。

**Architecture:** 在 `channels/router.py` 接入当前 actor，并把 ClawBot 节点列表、二维码、状态、删除，以及会话列表与会话更新统一改成基于 owner 过滤。owner 解析规则为：游客固定 `guest`、普通用户使用自身 `user_id`、管理员允许跨 owner 管理。

**Tech Stack:** FastAPI、SQLModel、pytest、TestClient

---

### Task 1: 补权限回归测试

**Files:**
- Modify: `tests/test_channels_router.py`
- Test: `tests/test_channels_router.py`

- [ ] **Step 1: Write the failing test**

```python
def test_weixin_clawbot_user_management_respects_actor_scope(monkeypatch):
    ...
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_channels_router.py -q`
Expected: 与 actor 作用域相关的断言失败，证明当前路由未做权限控制。

- [ ] **Step 3: Write minimal implementation**

```python
def _resolve_channel_owner(...):
    ...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_channels_router.py -q`
Expected: 新增权限测试通过。

### Task 2: 修复渠道路由权限控制

**Files:**
- Modify: `langchain_api/web_backend/channels/router.py`
- Modify: `langchain_api/web_backend/channels/store.py`
- Test: `tests/test_channels_router.py`

- [ ] **Step 1: Write the failing test**

```python
def test_session_routes_respect_actor_scope():
    ...
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_channels_router.py -q`
Expected: 会话列表或会话更新未按 actor 过滤，断言失败。

- [ ] **Step 3: Write minimal implementation**

```python
def list_sessions(..., user_id: str | None = None):
    ...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_channels_router.py -q`
Expected: 会话权限测试通过，原有会话功能保持可用。

### Task 3: 运行仓库要求的验证

**Files:**
- Modify: `langchain_api/web_backend/channels/router.py`
- Modify: `langchain_api/web_backend/channels/store.py`
- Modify: `tests/test_channels_router.py`

- [ ] **Step 1: Run Python syntax check**

Run: `uv run python -m py_compile langchain_api/web_backend/channels/router.py langchain_api/web_backend/channels/store.py tests/test_channels_router.py`
Expected: 无输出，退出码为 0。

- [ ] **Step 2: Run targeted tests**

Run: `uv run pytest tests/test_channels_router.py -q`
Expected: 相关测试全部通过。

- [ ] **Step 3: Run Ruff**

Run: `uv run ruff check .`
Expected: 无错误，退出码为 0。

- [ ] **Step 4: Refresh CodeGraph index**

Run: `codegraph index --force`
Expected: 索引成功刷新。
