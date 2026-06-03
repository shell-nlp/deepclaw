# Channel Gateway Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement an in-repository channel gateway that maps Feishu/DingTalk messages to the existing agent API with SQLite-backed SQLModel session configuration.

**Architecture:** Add a focused `langchain_api.channels` package with models, store, service orchestration, agent SSE client, response dispatcher, and placeholder adapters. Register `/api/channels/*` routes from `main.py`.

**Tech Stack:** FastAPI, SQLModel, SQLite, httpx-compatible SSE parsing via standard async iteration, Pydantic models.

**Constraints:** Do not commit. Do not add a new test framework. Use Python standard-library `unittest` for test-first coverage.

---

### Task 1: Channel Models And Store

**Files:**
- Create: `langchain_api/channels/__init__.py`
- Create: `langchain_api/channels/models.py`
- Create: `langchain_api/channels/store.py`
- Create: `tests/test_channels_store.py`

- [ ] Write failing `unittest` coverage for creating users, sessions, message records, and invalid `reply_mode`.
- [ ] Run `uv run python -m unittest tests.test_channels_store` and verify it fails because channels modules do not exist.
- [ ] Create SQLModel tables `ChannelUser`, `ChannelSession`, and `ChannelMessageRecord`.
- [ ] Create Pydantic models `ChannelMessage`, `AgentEvent`, `ReplyMode`, and session update/list response models.
- [ ] Implement `ChannelStore` with default SQLite URL `<home_path>/channels.db`.
- [ ] Implement lookup/create methods using logical keys:
  - `channel + channel_user_id`
  - `channel + channel_conversation_id + channel_user_id`
  - `channel + message_id`
- [ ] Validate `reply_mode` as only `final` or `streaming`.
- [ ] Run `uv run python -m unittest tests.test_channels_store` and verify it passes.

Verification:

```bash
uv run python -m py_compile langchain_api/channels/models.py langchain_api/channels/store.py
```

### Task 2: Agent Client

**Files:**
- Create: `langchain_api/channels/agent_client.py`

- [ ] Implement `AgentClient.stream()` that POSTs to `/api/agent/general_api`.
- [ ] Parse SSE lines shaped as `data: {...}` into `StreamResponse`.
- [ ] Yield normalized `AgentEvent` values.
- [ ] Allow dependency injection of a custom async sender for tests and for internal service usage.

Verification:

```bash
uv run python -m py_compile langchain_api/channels/agent_client.py
```

### Task 3: Dispatcher And Adapters

**Files:**
- Create: `langchain_api/channels/adapters/__init__.py`
- Create: `langchain_api/channels/adapters/base.py`
- Create: `langchain_api/channels/adapters/feishu.py`
- Create: `langchain_api/channels/adapters/dingtalk.py`
- Create: `langchain_api/channels/dispatcher.py`
- Create: `tests/test_channels_dispatcher.py`

- [ ] Write failing `unittest` coverage for final buffering, streaming throttled edits, and interrupt fallback.
- [ ] Run `uv run python -m unittest tests.test_channels_dispatcher` and verify it fails because dispatcher code does not exist.
- [ ] Define `ChannelAdapter` protocol with `parse_event`, `send_message`, and `edit_message`.
- [ ] Implement Feishu/DingTalk placeholder adapters that parse a simple normalized JSON body for initial integration.
- [ ] Implement `ResponseDispatcher.dispatch()` for `final` and `streaming` modes.
- [ ] Throttle streaming edits with time and character thresholds.
- [ ] Hide `tool_calls` and `tool_output` from channel users.
- [ ] Convert `__interrupt__` into a visible unsupported manual-confirmation message.
- [ ] Run `uv run python -m unittest tests.test_channels_dispatcher` and verify it passes.

Verification:

```bash
uv run python -m py_compile langchain_api/channels/adapters/base.py langchain_api/channels/adapters/feishu.py langchain_api/channels/adapters/dingtalk.py langchain_api/channels/dispatcher.py
```

### Task 4: Channel Service

**Files:**
- Create: `langchain_api/channels/service.py`
- Create: `tests/test_channels_service.py`

- [ ] Write failing `unittest` coverage for idempotent duplicate messages and creating channel user/session mappings.
- [ ] Run `uv run python -m unittest tests.test_channels_service` and verify it fails because service code does not exist.
- [ ] Implement idempotency using `ChannelMessageRecord`.
- [ ] Find or create `ChannelUser` and `ChannelSession`.
- [ ] Serialize processing by `session_id` with in-process `asyncio.Lock`.
- [ ] Call `AgentClient.stream()`.
- [ ] Call `ResponseDispatcher.dispatch()`.
- [ ] Mark records `processing`, `done`, or `failed`.
- [ ] Run `uv run python -m unittest tests.test_channels_service` and verify it passes.

Verification:

```bash
uv run python -m py_compile langchain_api/channels/service.py
```

### Task 5: API Router

**Files:**
- Create: `langchain_api/api/routers/channels.py`
- Modify: `langchain_api/main.py`

- [ ] Add `POST /api/channels/feishu/events`.
- [ ] Add `POST /api/channels/dingtalk/events`.
- [ ] Add `GET /api/channels/sessions`.
- [ ] Add `PATCH /api/channels/sessions/{session_id}`.
- [ ] Register the router in `create_app()`.

Verification:

```bash
uv run python -m py_compile langchain_api/api/routers/channels.py langchain_api/main.py
```

### Task 6: Final Verification

**Files:**
- All changed Python files.

- [ ] Run `uv run python -m py_compile` on all changed Python files.
- [ ] Run a lightweight import check for the new router.
- [ ] Confirm `git status --short` shows uncommitted changes only.

Verification:

```bash
uv run python -m py_compile langchain_api/channels/models.py langchain_api/channels/store.py langchain_api/channels/agent_client.py langchain_api/channels/dispatcher.py langchain_api/channels/service.py langchain_api/api/routers/channels.py langchain_api/main.py
uv run python -m unittest tests.test_channels_store tests.test_channels_dispatcher tests.test_channels_service
uv run python -c "from langchain_api.api.routers.channels import create_channels_router; print(create_channels_router)"
git status --short
```
