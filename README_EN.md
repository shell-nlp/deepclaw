<p align="right">
  <strong>🇨🇳 <a href="README.md">中文</a></strong> | 🇬🇧 English
</p>

<p align="center">
  <img src="assets/img/logo.png" alt="DeepClaw" width="360">
</p>

<p align="center">
  <strong>A ready-to-deploy enterprise agent workspace</strong><br>
  One FastAPI process serving the AG-UI runtime, knowledge bases, skills, channels and the frontend
</p>

<p align="center">
  <a href="#"><img alt="License" src="https://img.shields.io/badge/license-Apache--2.0-blue?style=flat-square"></a>
  <a href="#"><img alt="FastAPI" src="https://img.shields.io/badge/FastAPI-0.115-009688?style=flat-square&logo=fastapi&logoColor=white"></a>
  <a href="#"><img alt="LangGraph" src="https://img.shields.io/badge/LangGraph-Agent-1C3C3C?style=flat-square"></a>
  <a href="#"><img alt="AG-UI" src="https://img.shields.io/badge/AG--UI-Protocol-4D6BFE?style=flat-square"></a>
  <a href="#"><img alt="Next.js" src="https://img.shields.io/badge/Next.js-15-000000?style=flat-square&logo=nextdotjs&logoColor=white"></a>
  <a href="#"><img alt="PostgreSQL" src="https://img.shields.io/badge/PostgreSQL-pgvector-4169E1?style=flat-square&logo=postgresql&logoColor=white"></a>
</p>

<p align="center">
  <a href="#quick-start">Quick Start</a>
  ·
  <a href="#core-features">Core Features</a>
  ·
  <a href="#screenshots">Screenshots</a>
  ·
  <a href="#api-endpoints">API</a>
  ·
  <a href="#configuration">Configuration</a>
  ·
  <a href="#project-structure">Structure</a>
</p>

DeepClaw turns the "agent runtime" and everything around it into one deployable service: the browser and IM
channels speak the same AG-UI run protocol, general and RAG agents are selected by a single top-level
`agentId`, conversation state is persisted by LangGraph checkpoints, and the frontend build output is served
by the same process.

It fits these situations:

- You need one unified entry point for several business agents (general assistant, knowledge base Q&A, your own agents later).
- You need to wire agents into internal channels such as Feishu / DingTalk / WeChat, with multiple bindings per user.
- You need human approval before tool execution, or the agent needs to ask the user a question mid-run.
- You need private deployment: any OpenAI-compatible model gateway, your own PostgreSQL for state.

## Core Features

| Feature | Description |
|---------|-------------|
| Unified AG-UI runtime | Browser and channels both call `/api/agui/runs`; the top-level `agentId` picks the agent; SSE streaming with `Last-Event-ID` replay |
| Automatic agent discovery | Add `deepclaw/agents/<name>/agent.py` with an `Agent` subclass and the registry picks it up — no routing changes |
| Sessions and state | Thread ownership, run records, event cache and graph state all live in LangGraph checkpoints plus PostgreSQL, shared across instances |
| General agent | Built on LangGraph / DeepAgents with weather, web fetch and search tools, plus MCP config and skill packages |
| RAG knowledge base | Knowledge base creation, document upload, chunk inspection, graph retrieval, and a dedicated RAG agent |
| Multimodal input | AG-UI `messages` accept text plus image content blocks, converted by the adapter before reaching the model |
| Human in the loop | Per-tool approval with approve / edit / reject; interrupts are exposed via `RUN_FINISHED.outcome` and resumed with the standard `resume[]` |
| Skill management | List, upload and delete skill packages stored in the workspace skills directory |
| Channels | Feishu, DingTalk and WeChat ClawBot built in, with "binding" as the multi-user boundary |
| Chart tool | Nine matplotlib chart renderers with an optional public URL prefix, served directly by the service |
| Scheduled tasks (optional) | `CronMiddleware` exposes add / list / remove cron jobs as agent tools, but it is not enabled by default |
| Auth and guest mode | Opaque access tokens (SHA-256 at rest, revocable immediately) with admin/user roles; unauthenticated requests fall back to a guest identity |
| Execution backends | `local_shell`, `store` and `sandbox` |
| Multi-user sandbox isolation | In `sandbox` mode each user gets a dedicated OpenSandbox container; workspaces and history are isolated while shared skills/memory can be configured |
| Frontend | Next.js + React chat UI, built and served by FastAPI at `/` |
| Observability | Optional Phoenix tracing, Postgres long-term memory and Tavily search |

## Screenshots

These cover the main workflows: chat with streaming tool calls, human approval, knowledge bases, skills,
MCP management, the channel binding center and user management. Images live in `assets/img/` and can be
replaced after UI changes.

### Chat

![Chat](assets/img/chat.png)

The single entry point for agent conversations, streaming tool output and core interactions.

### Human in the Loop

![Human in the Loop](assets/img/human_in_the_loop.png)

The approval and argument-editing flow once a tool call requires human confirmation.

### Knowledge Base Management

![Knowledge Base](assets/img/knowledge_base.png)

Knowledge base list, library detail, paginated documents and chunk details.

### Skill Management

![Skill Management](assets/img/skill_management.png)

Upload, delete and maintain skill packages in the workspace skills directory.

### MCP Management

![MCP Management](assets/img/mcp_management.png)

Maintain MCP configuration and control whether general agent requests carry MCP server definitions.

### Channel Management

![Channel Management](assets/img/channels_management.png)

A unified binding center: one user can hold multiple Feishu / WeChat bindings, each with its own QR code,
status and delete action.

### User Management

![User Management](assets/img/user_management.png)

Admins can create users, change roles, enable/disable accounts and reset passwords; disabling or resetting
immediately revokes every token of that user.

## Tech Stack

| Layer | Technology |
|-------|------------|
| Web framework | FastAPI + Uvicorn |
| Agents | LangGraph, LangChain, DeepAgents, ag-ui-langgraph |
| Protocol | AG-UI (HTTP + SSE) |
| RAG | PostgreSQL + pgvector + pg_search, or Elasticsearch (dense vector + BM25); Graph RAG supports Elasticsearch / PostgreSQL and graph DB supports Neo4j / NetworkX |
| State | LangGraph checkpoints (PostgreSQL / in-memory), run & thread event tables (PostgreSQL / SQLite / in-memory), AsyncPostgresStore / InMemoryStore |
| Frontend | Next.js 15, React 19, TypeScript, CSS Modules |
| Execution backends | Local Shell, Store Backend, OpenSandbox (Docker sandbox) |
| Auth | Opaque access tokens (`hashlib.scrypt` password hashing + SHA-256 token hashing) |
| Optional | Phoenix, Tavily, OpenSandbox Server |
| Tooling | uv, pnpm |

## Project Structure

```text
deepclaw/
├── deepclaw/
│   ├── agent_registry.py    # Agent base class and auto-discovery registry
│   ├── agents/              # Agent implementations: general/, rag/
│   ├── common/              # Vector stores, Graph DB / Graph RAG, Docling parsing and text splitting
│   ├── middleware/          # Business toggles, MCP, charts, NL2SQL, memory, Python execution, sandbox
│   ├── patch/               # Third-party patches and adapters
│   ├── sandbox/             # OpenSandbox execution backend
│   ├── tools/               # Weather, web fetch, search, ask_user
│   ├── utils/               # Model factory, time helpers, token counting
│   ├── web_backend/         # FastAPI app layer: agui / agent / auth / channels / common / skills / knowledge_bases
│   ├── constant.py          # Module-level constants such as paths
│   ├── main.py              # Main entry point
│   └── settings.py          # Environment configuration
├── frontend/                # Next.js frontend (app/ source, out/ served statically by the backend)
├── mcp2tool/                # FastMCP to LangChain tool adapter
├── docker/                  # Middleware image build files such as PostgreSQL
├── assets/                  # README logo and screenshots
├── docs/                    # Design docs and historical archive
├── tests/                   # pytest suite
├── .deepclaw/               # Runtime workspace: skills, charts, uploads, SQLite fallbacks
├── user_workspace/          # Per-user workspace dirs (sandbox mode)
├── .env.example             # Environment variable template (do not commit .env)
├── .sandbox.toml            # OpenSandbox Server config (required in sandbox mode)
├── docker-compose.middleware.yml  # Middleware: PostgreSQL / Elasticsearch / Phoenix / Neo4j
├── docker-compose.app.yml         # Application: the deepclaw service
├── Dockerfile                     # Main service image
├── Dockerfile.code-interpreter-rebuild  # OpenSandbox code interpreter image rebuild
└── pyproject.toml                 # Dependencies and optional extras
```

> Frontend components are being organized under `frontend/components/chat/`; the legacy
> `frontend/components/chat-interface/` directory is still being migrated.

## System Architecture

```text
Browser  ·  Feishu  ·  DingTalk  ·  WeChat ClawBot
                    │
                    ▼
        POST /api/agui/runs          Unified AG-UI entry, top-level agentId selects the agent
        GET  /api/agui/agents        Available agents
                    │
                    ▼
┌───────────────────────────────────────────────────────────────────┐
│ FastAPI app layer (deepclaw/web_backend)                          │
│                                                                   │
│   /api/auth/*       Auth: register, login, logout, users & roles   │
│   /api/agui/*       AG-UI: runs, threads, SSE stream and replay    │
│   /api/agent/*      Skill management                               │
│   /api/rag/*        Knowledge bases and documents                  │
│   /api/channels/*   Channel bindings and sessions                  │
│   /api/runtime-config  Frontend runtime paths                      │
└───────────────────────────────────────────────────────────────────┘
                    │
                    ▼
┌───────────────────────────────────────────────────────────────────┐
│ Agent runtime                                                      │
│                                                                   │
│   AgentRegistry auto-discovery → AgentRuntimeCache caches per agent│
│     ├─ agent   General agent: tools / MCP / skills / charts / HITL │
│     └─ rag     Knowledge agent: RAGMiddleware retrieval & rewrite  │
│                                                                   │
│   LangGraph checkpoint + store hold state, memory and message times│
└───────────────────────────────────────────────────────────────────┘
                    │
                    ▼
┌───────────────────────────────────────────────────────────────────┐
│ Infrastructure                                                     │
│                                                                   │
│   PostgreSQL      State, events, metadata, pgvector (optional)     │
│   Elasticsearch   Vector + keyword retrieval (VECTOR_STORE_BACKEND)│
│   SQLite          Fallback when PostgreSQL is not configured       │
│   Docker          OpenSandbox containers (BACKEND_TYPE=sandbox)    │
│   LLM gateway     Any OpenAI-compatible endpoint                   │
│   Phoenix         Distributed tracing (optional)                   │
└───────────────────────────────────────────────────────────────────┘
```

## Quick Start

### 1. Prerequisites

| Scenario | Requirements |
|----------|--------------|
| Run backend and prebuilt frontend | Python `>= 3.12`, `uv`, Docker / Docker Compose |
| Develop or rebuild the frontend | Additionally Node.js `>= 18` and `pnpm` |

If `frontend/out` already exists and you are not changing frontend code, you can skip the frontend steps.

### 2. Initialize the backend

```bash
cp .env.example .env
uv sync --dev
```

Add optional capabilities as needed:

```bash
uv sync --dev --extra pdf           # Knowledge base ingestion (text to PDF and parsing)
uv sync --dev --extra docling       # Docling document parsing
uv sync --dev --extra elasticsearch # Elasticsearch vector store
uv sync --dev --extra web-fetch     # Crawl4AI web fetch
uv sync --dev --extra mem0          # Mem0 long-term memory
uv sync --dev --extra oracle        # Oracle DDL fetcher
uv sync --dev --extra opensandbox   # sandbox execution backend
uv sync --dev --extra feishu        # Feishu long connection
uv sync --dev --extra phoenix       # Phoenix observability
uv sync --dev --extra object-storage # MinIO / S3 object storage
```

> Knowledge base uploads require the `pdf` extra. Without it the API returns
> `PDF 解析需要 PyMuPDF，请执行 uv sync --extra pdf 安装`.

### 3. Configure `.env`

Required values (everything else has a default):

```dotenv
OPENAI_API_BASE=http://localhost:8082/v1
OPENAI_API_KEY=your-api-key
CHAT_MODEL_NAME=qwen3
EMBEDDING_MODEL_NAME=qwen3-embedding
```

Configure storage and retrieval for your deployment:

```dotenv
# General agent only: PostgreSQL is optional; runs/threads/checkpoints live in memory and are lost on restart.
# Knowledge bases / RAG need a vector store. Pick one:

# Option A: PostgreSQL + pgvector
PG_DATABASE_URL=postgresql://admin:admin@localhost:5432/deepclaw
VECTOR_STORE_BACKEND=pgsql

# Option B: Elasticsearch
# VECTOR_STORE_BACKEND=elasticsearch
# ES_URL=http://localhost:9200
# ES_URSR=elastic
# ES_PWD=elastic@2024

# Knowledge base object storage: local by default, optionally MinIO
OBJECT_STORAGE_PROVIDER=local
# LOCAL_STORAGE_ROOT=.deepclaw/workspace/pdf_files
# OBJECT_STORAGE_PROVIDER=minio
# MINIO_ENDPOINT_URL=http://localhost:9000
# MINIO_ACCESS_KEY=minioadmin
# MINIO_SECRET_KEY=minioadmin
```

> Only with `PG_DATABASE_URL` set do runs, threads and checkpoints land in a shared database, which is what
> lets multiple instances share session state. Without it checkpoints live in memory and are lost on restart.

### 4. Start the main service

```bash
uv run python -m deepclaw.main
```

Once running:

- Frontend: `http://localhost:7869/`
- AG-UI runs: `POST /api/agui/runs`
- AG-UI agents: `GET /api/agui/agents`
- Channels API: `/api/channels/*`

On first start, if `AUTH_ADMIN_EMAIL` / `AUTH_ADMIN_PASSWORD` are set and no admin exists yet, that admin
account is created automatically. Unauthenticated requests fall back to a guest identity, and guests may
manage skills and knowledge bases.

### 5. Start dependencies (optional but recommended)

Elasticsearch knowledge bases or Postgres long-term memory need their services:

```bash
docker compose -f docker-compose.middleware.yml up -d postgresql elasticsearch
```

For Phoenix tracing:

```bash
docker compose -f docker-compose.middleware.yml up -d phoenix
```

To run the service itself in a container, middleware and app are composed separately:

```bash
docker compose -f docker-compose.middleware.yml up -d   # middleware first
docker compose -f docker-compose.app.yml up -d          # then the app
```

Phoenix console defaults to `http://localhost:6006`.

### 6. Start OpenSandbox Server (optional, sandbox mode only)

With `BACKEND_TYPE=sandbox` you also need OpenSandbox Server and the images:

```bash
# Pull required images
docker pull sandbox-registry.cn-zhangjiakou.cr.aliyuncs.com/opensandbox/code-interpreter:v1.0.2
docker pull opensandbox/execd:v1.0.16
docker pull opensandbox/egress:v1.0.12

# Start OpenSandbox Server (configure .sandbox.toml first)
opensandbox-server --config .sandbox.toml
```

### 7. Frontend development

Only needed when you are developing or rebuilding the frontend:

```bash
cd frontend
pnpm install
pnpm dev
```

Dev server: `http://localhost:3000`

Build the static frontend for the backend to serve:

```bash
cd frontend
pnpm build
```

## API Endpoints

Business endpoints accept guest access; without `Authorization: Bearer <token>` the request is handled as a
guest. User-management endpoints and admin-only scopes such as the full channel binding list require an admin
role and cannot be called as a guest.

### Auth

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/api/auth/register` | Register a regular user and return an access token |
| `POST` | `/api/auth/login` | Email and password login |
| `POST` | `/api/auth/logout` | Revoke the current access token |
| `GET` | `/api/auth/me` | Return the current actor |
| `POST` | `/api/auth/users/create` | Admin: create a user with a role |
| `POST` | `/api/auth/users/list` | Admin: list users |
| `POST` | `/api/auth/users/update-role` | Admin: change a user role |
| `POST` | `/api/auth/users/update-status` | Admin: enable or disable a user |
| `POST` | `/api/auth/users/reset-password` | Admin: reset a user password |

Access tokens are server-side opaque tokens (`la_` prefix plus random bytes; only the SHA-256 hash is
stored) and expire after one day by default. Disabling a user or resetting a password revokes all of that
user's tokens immediately.

### Runtime config

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/api/runtime-config` | AG-UI runs and agents paths used by the frontend |

### AG-UI (unified Agent/RAG)

| Method | Path | Protocol | Purpose |
|--------|------|----------|---------|
| `GET` | `/api/agui/agents` | REST | List available agents |
| `POST` | `/api/agui/runs` | AG-UI | Create a run; select the agent with top-level `agentId` |
| `GET` | `/api/agui/runs/{run_id}/events` | AG-UI SSE | Replay or continue run events |
| `GET` | `/api/agui/runs/{run_id}` | REST | Run snapshot |
| `POST` | `/api/agui/runs/{run_id}/resume` | AG-UI | Resume an interrupted run |
| `POST` | `/api/agui/runs/{run_id}/cancel` | REST | Cancel a run |
| `GET` | `/api/agui/threads` | REST | List threads |
| `GET` | `/api/agui/threads/{thread_id}/runs` | REST | List runs in a thread |
| `GET` | `/api/agui/threads/{thread_id}/state` | REST | Thread graph state |
| `DELETE` | `/api/agui/threads/{thread_id}` | REST | Delete a thread |

### Agent management

| Method | Path | Protocol | Purpose |
|--------|------|----------|---------|
| `POST` | `/api/agent/skills/list` | REST | List skills |
| `POST` | `/api/agent/skills/upload` | REST | Upload a skill zip |
| `POST` | `/api/agent/skills/delete` | REST | Delete a skill |

### Knowledge base

| Method | Path | Protocol | Purpose |
|--------|------|----------|---------|
| `POST` | `/api/rag/knowledge-bases/list` | REST | Paginated knowledge base list |
| `POST` | `/api/rag/knowledge-bases/create` | REST | Create a knowledge base |
| `POST` | `/api/rag/knowledge-bases/detail` | REST | Knowledge base detail |
| `POST` | `/api/rag/knowledge-bases/update` | REST | Update a knowledge base |
| `POST` | `/api/rag/knowledge-bases/delete` | REST | Delete a knowledge base |
| `POST` | `/api/rag/knowledge-bases/bulk-delete` | REST | Bulk delete knowledge bases |
| `POST` | `/api/rag/knowledge-bases/documents/list` | REST | Paginated document list |
| `POST` | `/api/rag/knowledge-bases/documents/detail` | REST | Document chunk detail |
| `POST` | `/api/rag/knowledge-bases/documents/upload` | REST | Upload documents |
| `POST` | `/api/rag/knowledge-bases/documents/update` | REST | Rename a document |
| `POST` | `/api/rag/knowledge-bases/documents/delete` | REST | Delete a document |
| `POST` | `/api/rag/knowledge-bases/documents/bulk-delete` | REST | Bulk delete documents |

### Channels

| Method | Path | Protocol | Purpose |
|--------|------|----------|---------|
| `GET` | `/api/channels/bindings` | REST | List channel bindings (`scope=my\|all`) |
| `POST` | `/api/channels/feishu/events` | REST | Feishu event entry |
| `POST` | `/api/channels/feishu/bindings` | REST | Create a Feishu binding |
| `DELETE` | `/api/channels/feishu/bindings/{binding_id}` | REST | Delete a Feishu binding |
| `POST` | `/api/channels/dingtalk/events` | REST | DingTalk event entry |
| `POST` | `/api/channels/weixin-clawbot/bindings` | REST | Create a WeChat ClawBot binding |
| `POST` | `/api/channels/weixin-clawbot/bindings/{binding_id}/qrcode` | REST | Refresh binding QR code |
| `GET` | `/api/channels/weixin-clawbot/bindings/{binding_id}/qrcode/status` | REST | Query binding QR code status |
| `DELETE` | `/api/channels/weixin-clawbot/bindings/{binding_id}` | REST | Delete a WeChat ClawBot binding |
| `POST` | `/api/channels/weixin-clawbot/poll` | REST | Poll pending WeChat ClawBot messages |
| `GET` | `/api/channels/sessions` | REST | List channel sessions |
| `PATCH` | `/api/channels/sessions/{session_id}` | REST | Update session reply mode |

## Usage Examples

Examples assume the service runs at `http://localhost:7869`. Except for admin-only endpoints, business
requests may omit the `Authorization` header (treated as a guest).

### Obtain an access token

```bash
TOKEN=$(curl -s -X POST http://localhost:7869/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@example.com","password":"Admin123456"}' \
  | python -c "import json,sys; print(json.load(sys.stdin)['token'])")
```

### General agent Q&A

`agentId` may be omitted to use the default `agent`. `threadId` scopes the conversation; reusing it
continues the same history.

```bash
curl -X POST http://localhost:7869/api/agui/runs \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "agentId": "agent",
    "threadId": "demo-thread",
    "runId": "run-demo-1",
    "state": {
      "internet_search": false,
      "deep_thinking": true
    },
    "messages": [
      { "id": "msg-1", "role": "user", "content": "What is the weather in Shanghai tomorrow?" }
    ],
    "tools": [],
    "context": [],
    "forwardedProps": {}
  }'
```

The response is `202` with a run snapshot (`runId` / `threadId` / `agentId` / `status` / `lastEventId`).

### Subscribe to the event stream

```bash
curl -N http://localhost:7869/api/agui/runs/run-demo-1/events \
  -H "Authorization: Bearer $TOKEN" \
  -H "Last-Event-ID: run-demo-1:12"
```

Events are standard AG-UI events (`TEXT_MESSAGE_CONTENT`, `TOOL_CALL_START`, `TOOL_CALL_RESULT`, ...).
Passing `Last-Event-ID` replays from that sequence number so reconnects do not lose events.

### Resume an interrupt (human in the loop)

When a tool call requires approval the service reports the interrupt through `RUN_FINISHED.outcome`.
Resume the **same run** by putting the decision in the top-level `resume[]`:

```bash
curl -X POST http://localhost:7869/api/agui/runs/run-demo-1/resume \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "agentId": "agent",
    "threadId": "demo-thread",
    "runId": "run-demo-1",
    "messages": [
      { "id": "msg-1", "role": "user", "content": "Check the weather in Nanyang tomorrow" }
    ],
    "resume": [
      {
        "interruptId": "interrupt-1",
        "status": "resolved",
        "payload": { "decisions": [ { "type": "approve" } ] }
      }
    ]
  }'
```

### Knowledge base Q&A

`index_name` and `graph_name` come from the knowledge base detail fields `passage_index` and `index_prefix`:

```bash
curl -X POST http://localhost:7869/api/agui/runs \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "agentId": "rag",
    "threadId": "rag-thread",
    "runId": "rag-run-demo-1",
    "state": {
      "index_name": "kb_xxx_passages",
      "graph_name": "kb_xxx",
      "deep_thinking": false
    },
    "messages": [
      { "id": "msg-1", "role": "user", "content": "What is the core conclusion of this document?" }
    ],
    "tools": [],
    "context": [],
    "forwardedProps": {}
  }'
```

### Create a knowledge base and upload documents

```bash
# Create a knowledge base (the owner is derived server-side from the token; guests map to `guest`)
curl -X POST http://localhost:7869/api/rag/knowledge-bases/create \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"user_id":"demo-user","name":"Product Docs","description":"Example knowledge base"}'

# Upload a document (requires uv sync --extra pdf)
curl -X POST http://localhost:7869/api/rag/knowledge-bases/documents/upload \
  -H "Authorization: Bearer $TOKEN" \
  -F "user_id=demo-user" \
  -F "knowledge_base_id=<knowledge_base_id>" \
  -F "files=@./product-intro.md"
```

### Query threads

```bash
curl http://localhost:7869/api/agui/threads -H "Authorization: Bearer $TOKEN"
curl http://localhost:7869/api/agui/threads/demo-thread/runs -H "Authorization: Bearer $TOKEN"
curl http://localhost:7869/api/agui/threads/demo-thread/state -H "Authorization: Bearer $TOKEN"
```

`/state` returns the LangGraph graph state plus `message_created_at`
(`messageId -> UTC ISO8601`) so the frontend can show each message's real timestamp.

## Configuration

### Required environment variables

| Variable | Description |
|----------|-------------|
| `OPENAI_API_BASE` | OpenAI-compatible LLM gateway URL |
| `OPENAI_API_KEY` | LLM gateway key |
| `CHAT_MODEL_NAME` | Chat model name |
| `EMBEDDING_MODEL_NAME` | Embedding model used for knowledge base ingestion and retrieval |

### Storage and retrieval

| Variable | Description |
|----------|-------------|
| `PG_DATABASE_URL` | PostgreSQL connection string. When set, runs/threads, checkpoints, long-term memory, auth, channels and knowledge base metadata all share one database and multiple instances can share state |
| `VECTOR_STORE_BACKEND` | Vector store backend: `pgsql` (PostgreSQL + pgvector) or `elasticsearch`; defaults to `elasticsearch` |
| `ES_URL` | Elasticsearch URL when `VECTOR_STORE_BACKEND=elasticsearch` |
| `ES_URSR` / `ES_PWD` | Elasticsearch username and password |
| `OBJECT_STORAGE_PROVIDER` | Knowledge-base file storage: `local` (default) or `minio` |
| `LOCAL_STORAGE_ROOT` | Local object-storage root, default `.deepclaw/workspace/pdf_files`; paths are `root/bucket_name/file_path` |
| `MINIO_ENDPOINT_URL` / `MINIO_ACCESS_KEY` / `MINIO_SECRET_KEY` | Required when `OBJECT_STORAGE_PROVIDER=minio` |

### Common optional environment variables

| Variable | Description |
|----------|-------------|
| `HOST` / `PORT` | Listen address and port, defaults to `0.0.0.0:7869` |
| `BACKEND_TYPE` | Execution backend: `local_shell` (default) / `store` / `sandbox` |
| `OPEN_SANDBOX_CODE_INTERPRETER_IMAGE` | Sandbox code interpreter image (default `sandbox-registry.cn-zhangjiakou.cr.aliyuncs.com/opensandbox/code-interpreter:v1.0.2`) |
| `TAVILY_API_KEY` | Enables the web search tool |
| `USE_TOOL_SEARCH` | Enables deferred tool search |
| `USE_COPILOTKIT` | Enables the CopilotKit middleware |
| `MCP_CONFIG` | Default MCP server configuration (JSON) |
| `PHOENIX_COLLECTOR_ENDPOINT` | Enables Phoenix tracing |
| `AUTH_ADMIN_EMAIL` / `AUTH_ADMIN_PASSWORD` | Admin account bootstrapped on first start |
| `AUTH_TOKEN_EXPIRE_DAYS` | Access token lifetime in days, default `1` |
| `AGUI_RUN_RETENTION_SECONDS` | Run and event retention, default `3600` |
| `AGUI_RUN_MAX_EVENTS` | Max events per run, default `2000` |
| `AGUI_RUN_CLEANUP_INTERVAL_SECONDS` | Expired-record cleanup interval, default `60` |
| `AGUI_RUN_POLL_INTERVAL_SECONDS` | Event stream poll interval, default `0.5` |
| `CHART_PUBLIC_URL` | Public URL prefix for charts; empty returns a relative `/charts/xxx.png` |
| `CHART_RETENTION_HOURS` / `CHART_MAX_FILES` | Chart file retention and count limits |
| `CHANNEL_AGENT_API_URL` | Full URL channels use to reach the agent; when empty the current service's `/api/agui/runs` is used |
| `WEIXIN_CLAWBOT_*` | WeChat ClawBot settings |

## Sandbox Mode (Multi-User Work Isolation)

With `BACKEND_TYPE=sandbox`, DeepClaw uses [OpenSandbox](https://github.com/opensandbox/opensandbox) to give
each user a dedicated Docker container as the execution environment.

### Isolation mechanism

| Dimension | Description |
|-----------|-------------|
| Container | Each user gets a dedicated OpenSandbox container; processes and filesystem are fully isolated |
| Workspace | Each user's workspace maps to `user_workspace/{user_id}/.deepclaw/` via a Docker bind mount |
| Skills | The private skills directory (`/.deepclaw/workspace/skills`) is mounted per user while shared skills (`/workspace/skills`) stay common |
| History | Conversation history is written to a per-user `conversation_history` directory |
| Lifecycle | After each agent execution `OpenSandboxKillMiddleware` kills the user's sandbox and cleans up state |

### Execution flow

1. On startup the agent checks `BACKEND_TYPE` and loads the `OpenSandbox` backend when it is `sandbox`.
2. On first execution `get_sandbox()` creates a sandbox for the current `user_id` and persists `sandbox_id` in the runtime store.
3. Later executions reuse the existing sandbox by reconnecting with `sandbox_id`.
4. Inside the sandbox the agent can execute commands (`execute`), read/write files (`write`/`read`), edit files (`edit`) and upload/download files (`upload_files`/`download_files`).
5. When execution finishes, `OpenSandboxKillMiddleware.after_agent` kills the sandbox and removes the store record.

### Prerequisites

- Docker
- OpenSandbox Server running (see step 6 above)
- A valid `.sandbox.toml` (a sample ships with the repo)
- Install the extra: `uv sync --dev --extra opensandbox`

### Configuration file `.sandbox.toml`

```toml
[server]
host = "127.0.0.1"
port = 8089

[runtime]
type = "docker"
execd_image = "docker.1ms.run/opensandbox/execd:v1.0.16"

[storage]
allowed_host_paths = ["/path/to/deepclaw"]
```

`allowed_host_paths` must contain the absolute path to the project root, otherwise the bind mount is rejected.

## Notes

- The backend mounts `frontend/out` directly. When that directory exists, a pure runtime deployment needs neither Node.js nor pnpm.
- After frontend changes you must run `pnpm build` again before `/` serves the new page.
- The default workspace is `.deepclaw/workspace`, holding skill packages, charts and uploaded source files.
- Without `PG_DATABASE_URL`, auth, channels and knowledge base metadata each fall back to SQLite under
  `.deepclaw/` and checkpoints live in memory — **state is lost on restart and cannot be shared across
  instances**.
- Requests without a token are handled as a guest; guests may manage skills and knowledge bases, while only
  user management requires an admin role.
- All database access goes through SQLModel async sessions; do not introduce synchronous database calls in
  the web layer.
- If `frontend/out` is missing the API still works, but `/` will not serve the frontend.
- Sandbox mode (`BACKEND_TYPE=sandbox`) requires OpenSandbox Server and a valid `.sandbox.toml`; see the Sandbox Mode section above.
- Adding an agent needs no web routing changes: define an `Agent` subclass in
  `deepclaw/agents/<name>/agent.py` and it is discovered automatically. The frontend reads
  `GET /api/agui/agents` and calls it with the top-level `agentId`.
- `CronMiddleware` provides cron tools, but it is not enabled by default; add it explicitly to the agent's
  middleware list when needed.
- `.env` contains secrets and must not be committed to Git; the repository only keeps `.env.example`.

## License

Apache-2.0
