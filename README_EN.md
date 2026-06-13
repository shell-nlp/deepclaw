<p align="right">
  <a href="README.md">🇨🇳 中文</a> | <strong>🇬🇧 English</strong>
</p>

<h1 align="center">DeepClaw</h1>

<p align="center">
  <a href="#"><img alt="License" src="https://img.shields.io/badge/license-Apache--2.0-blue?style=flat-square"></a>
  <a href="#"><img alt="Python" src="https://img.shields.io/badge/Python-3.12%2B-3776AB?style=flat-square&logo=python&logoColor=white"></a>
  <a href="#"><img alt="FastAPI" src="https://img.shields.io/badge/FastAPI-0.115-009688?style=flat-square&logo=fastapi&logoColor=white"></a>
  <a href="#"><img alt="LangGraph" src="https://img.shields.io/badge/LangGraph-Agent-1C3C3C?style=flat-square"></a>
  <a href="#"><img alt="Next.js" src="https://img.shields.io/badge/Next.js-15-000000?style=flat-square&logo=nextdotjs&logoColor=white"></a>
  <a href="#"><img alt="Elasticsearch" src="https://img.shields.io/badge/Elasticsearch-8.x-005571?style=flat-square&logo=elasticsearch&logoColor=white"></a>
</p>

<p align="center">
  <a href="#quick-start">Quick Start</a>
  ·
  <a href="#core-features">Core Features</a>
  ·
  <a href="#screenshots">Screenshots</a>
  ·
  <a href="#api-endpoints">API Endpoints</a>
  ·
  <a href="#configuration">Configuration</a>
  ·
  <a href="#project-structure">Project Structure</a>
</p>

DeepClaw is an open-source Agent / RAG scaffold. It integrates general-purpose Agent, RAG knowledge bases, skill management, channel integration, MCP configuration, and a static frontend into a single FastAPI service — ideal for quickly building enterprise knowledge Q&A, automation assistants, internal Copilots, and multi-tool agent applications.

## Core Features

- **General Agent** — Built on LangGraph / DeepAgents with tool calling, SSE streaming output, and MCP configuration passthrough
- **RAG Knowledge Base** — Knowledge base creation, document upload, chunk inspection, graph retrieval RAG, and standalone RAG Q&A
- **Multimodal Input** — The unified `query` interface supports plain text and mixed text-image structures
- **Skill Management** — Skill listing, uploading, and deletion
- **Channel Integration** — Built-in Feishu (Lark), DingTalk, and WeChat ClawBot routing with session management
- **Multiple Execution Backends** — Supports `local_shell`, `store`, and `sandbox` execution modes
- **Multi-User Sandbox Isolation** — In `sandbox` mode, each user gets an independent OpenSandbox container; workspaces, skill directories, and conversation history are fully isolated
- **Frontend UI** — Next.js + React chat UI, served by FastAPI at `/` after build
- **Observability** — Optional Phoenix tracing, Postgres long-term memory, and Tavily search

## Screenshots

The following screenshots cover the project's main workflows, including chat, human-in-the-loop approval, knowledge bases, skill management, MCP management, channel management, and user isolation.

### Chat Interface

![Chat](assets/img/chat.png)

Unified interface for agent conversations, tool call streaming, and core interaction.

### Human in the Loop

![Human in the Loop](assets/img/human_in_the_loop.png)

Shows the approval and parameter editing flow when a tool call enters human review.

### Knowledge Base Management

![Knowledge Base](assets/img/knowledge_base.png)

For viewing knowledge base lists, details, document pagination, and chunk details.

### Skill Management

![Skill Management](assets/img/skill_management.png)

For uploading, deleting, and maintaining workspace skill directories.

### MCP Management

![MCP Management](assets/img/mcp_management.png)

For maintaining MCP configurations and controlling whether agent requests include MCP service definitions.

### Channel Management

![Channel Management](assets/img/channels_management.png)

For managing Feishu, DingTalk, and WeChat ClawBot channel integration, user binding, and reply modes.

### User Management

![User Management](assets/img/user_management.png)

For switching between and managing different user identities, isolating conversations, knowledge bases, and channel data.

## Tech Stack

| Module | Technology |
|--------|-----------|
| Backend | FastAPI, LangGraph, DeepAgents, LangChain |
| RAG | Elasticsearch, Dense Vector, BM25, Graph RAG |
| Frontend | Next.js 15, React 19, TypeScript |
| Execution Backend | Local Shell, Store Backend, OpenSandbox (Docker container sandbox) |
| Multi-User Isolation | Per-user isolated containers + bind mount volumes via OpenSandbox |
| Optional Components | Phoenix, Tavily, PostgresStore, OpenSandbox Server |
| Package Management | uv, pnpm |

## Project Structure

```text
deepclaw/
├── deepclaw/
│   ├── agents/              # General Agent / RAG Agent assembly, context, and state
│   ├── backend/             # Execution backends (including OpenSandbox sandbox isolation)
│   ├── common/              # Common utilities: Elasticsearch, Graph RAG, text splitting
│   ├── middleware/          # Middleware: feature flags, RAG injection, MCP, tool search, sandbox cleanup
│   ├── patch/               # Third-party library patches
│   ├── tools/               # Tools: weather, web fetch, search, cron jobs
│   ├── web_backend/         # FastAPI web application layer and all web feature directories
│   ├── main.py              # Main entry point
│   └── settings.py          # Environment variable configuration
├── frontend/                # Next.js frontend
├── .deepclaw/               # Runtime workspace, skill directories, channel database, etc.
├── .sandbox.toml            # OpenSandbox Server configuration (required for sandbox mode)
├── user_workspace/          # Per-user workspace directories (sandbox mode)
├── assets/                  # Screenshots and Elasticsearch plugins
└── docker-compose.yml       # PostgreSQL / Elasticsearch / Phoenix
```

## System Architecture

```text
┌──────────────────────────────────────────────────────────────────────┐
│                          Access Layer                                 │
│  ┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐     │
│  │  Next.js Frontend │ │  Feishu Adapter  │ │  DingTalk        │     │
│  │  (frontend/out)  │ │ (Long Conn+WS)   │ │ (Webhook)        │     │
│  └────────┬─────────┘ └────────┬─────────┘ └────────┬─────────┘     │
│  ┌──────────────────┐ ┌──────────────────┐          │               │
│  │  WeChat ClawBot   │ │  Other Channels  │          │               │
│  │ (QR+Polling)     │ │                  │          │               │
│  └────────┬─────────┘ └────────┬─────────┘          │               │
│           │                    │                    │               │
│           └────────────┬───────┴────────────────────┘               │
│                        ▼                                            │
└──────────────────────────────────────────────────────────────────────┘
              ┌──────────────────────────────────────────────────┐
              │  POST /api/agent/general_api                      │
              │  POST /api/rag/general_api                        │
              │  POST /api/auth/*                                 │
              │  POST /api/channels/sessions                      │
              └─────────────────────┬────────────────────────────┘
                                    │
┌──────────────────────────────────────────────────────────────────────┐
│                         API Layer / FastAPI                           │
│  ┌──────────┐ ┌──────────────┐ ┌──────────────┐ ┌────────────────┐  │
│  │Auth Route│ │ Agent Route  │ │  RAG Route   │ │Channel Mgmt   │  │
│  │/api/auth │ │ /api/agent   │ │ /api/rag     │ │/api/channels  │  │
│  └────┬─────┘ └──────┬───────┘ └──────┬───────┘ └───────┬────────┘  │
│       │              │               │                 │            │
└───────┼──────────────┼───────────────┼─────────────────┼────────────┘
        ▼              ▼               ▼                 ▼
┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐
│   Auth Service   │ │  General Agent   │ │   RAG Agent      │ │  Channel Service │
│   SQLModel       │ │ LangGraph+Agent  │ │   LangChain      │ │Binding·Session   │
└──────────────────┘ │  Middleware Pipe │ │   RAGMiddleware  │ │Dispatcher        │
                     │  Prompt→Biz→     │ └────────┬─────────┘ └──────────────────┘
                     │  MCP→RAG→Plan→   │          │
                     │  Cron→Sandbox    │          │
                     └────────┬─────────┘          │
                              │                    │
                              ▼                    ▼
┌──────────────────────────────────────────────────────────────────────┐
│                        Infrastructure                                │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐  │
│  │ES Vector │ │PostgreSQL│ │  SQLite  │ │  Docker  │ │LLM API   │  │
│  │+ Keyword │ │ Memory   │ │Channel   │ │ Sandbox  │ │OpenAI    │  │
│  │ Search   │ │Checkpoints│ │  Data    │ │Containers│ │Compatible│  │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘  │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │  Phoenix Distributed Tracing                                  │  │
│  └───────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────┘
```

## Quick Start

### 1. Prerequisites

| Scenario | Dependencies |
|----------|-------------|
| Run backend + pre-built frontend only | Python `>= 3.12`, `uv`, Docker / Docker Compose |
| Develop or rebuild the frontend | Additional Node.js `>= 18`, `pnpm` |

If `frontend/out` already exists in the repository and you are not modifying frontend code, you can skip the frontend installation and build steps.

### 2. Initialize Backend

```bash
cp .env.example .env
uv sync --dev
```

To enable OpenSandbox:

```bash
uv sync --dev --extra opensandbox
```

### 3. Configure `.env`

At minimum, fill in:

```dotenv
OPENAI_API_KEY=your-api-key
OPENAI_API_BASE=http://localhost:8082/v1
CHAT_MODEL_NAME=qwen3
EMBEDDING_MODEL_NAME=qwen3-embedding
ES_URL=http://localhost:9200
ES_URSR=elastic
ES_PWD=elastic@2024
```

### 4. Start the Main Service

Start from the unified `main` entry point:

```bash
uv run python -m deepclaw.main
```

After the service starts:

- Frontend: `http://localhost:7869/`
- Agent SSE: `POST /api/agent/general_api`
- Agent AG-UI: `POST /api/agent/ag_ui`
- RAG SSE: `POST /api/rag/general_api`
- Channels API: `/api/channels/*`

### 5. Start Dependencies (optional but recommended)

If you need Elasticsearch knowledge bases or Postgres long-term memory, start the required services:

```bash
docker-compose up -d postgresql elasticsearch
```

For Phoenix observability:

```bash
docker-compose up -d phoenix
```

Phoenix console: `http://localhost:6006`

### 6. Start OpenSandbox Server (optional, sandbox mode only)

If using `BACKEND_TYPE=sandbox`, you need to start OpenSandbox Server and pull the required images:

```bash
# Pull required images
docker pull sandbox-registry.cn-zhangjiakou.cr.aliyuncs.com/opensandbox/code-interpreter:v1.0.2
docker pull opensandbox/execd:v1.0.16
docker pull opensandbox/egress:v1.0.12

# Start OpenSandbox Server (configure .sandbox.toml first)
opensandbox-server --config .sandbox.toml
```

### 7. Frontend Development

Only needed if you are developing or rebuilding the frontend:

```bash
cd frontend
pnpm install
pnpm dev
```

Dev mode address: `http://localhost:3000`

Build the static frontend for backend hosting:

```bash
cd frontend
pnpm build
```

## API Endpoints

### Agent

| Method | Path | Protocol | Description |
|--------|------|----------|-------------|
| `POST` | `/api/agent/ag_ui` | AG-UI | Agent frontend protocol interface |
| `POST` | `/api/agent/general_api` | SSE | General Agent streaming interface |
| `POST` | `/api/agent/skills/list` | REST | List skills |
| `POST` | `/api/agent/skills/upload` | REST | Upload skill zip |
| `POST` | `/api/agent/skills/delete` | REST | Delete skill |

### RAG

| Method | Path | Protocol | Description |
|--------|------|----------|-------------|
| `POST` | `/api/rag/general_api` | SSE | RAG streaming Q&A |
| `POST` | `/api/rag/knowledge-bases/list` | REST | Paginated knowledge base list |
| `POST` | `/api/rag/knowledge-bases/create` | REST | Create knowledge base |
| `POST` | `/api/rag/knowledge-bases/detail` | REST | Knowledge base details |
| `POST` | `/api/rag/knowledge-bases/update` | REST | Update knowledge base |
| `POST` | `/api/rag/knowledge-bases/delete` | REST | Delete knowledge base |
| `POST` | `/api/rag/knowledge-bases/bulk-delete` | REST | Bulk delete knowledge bases |
| `POST` | `/api/rag/knowledge-bases/documents/list` | REST | Paginated document list |
| `POST` | `/api/rag/knowledge-bases/documents/detail` | REST | Document chunk details |
| `POST` | `/api/rag/knowledge-bases/documents/upload` | REST | Upload document |
| `POST` | `/api/rag/knowledge-bases/documents/update` | REST | Update document display name |
| `POST` | `/api/rag/knowledge-bases/documents/delete` | REST | Delete document |
| `POST` | `/api/rag/knowledge-bases/documents/bulk-delete` | REST | Bulk delete documents |

### Channels

| Method | Path | Protocol | Description |
|--------|------|----------|-------------|
| `POST` | `/api/channels/feishu/events` | REST | Feishu event entry |
| `POST` | `/api/channels/dingtalk/events` | REST | DingTalk event entry |
| `POST` | `/api/channels/weixin-clawbot/qrcode` | REST | Get WeChat ClawBot login QR code |
| `GET` | `/api/channels/weixin-clawbot/qrcode/status` | REST | Query QR code status |
| `POST` | `/api/channels/weixin-clawbot/users/{user_id}/qrcode` | REST | Generate user binding QR code |
| `GET` | `/api/channels/weixin-clawbot/users` | REST | List bound users |
| `DELETE` | `/api/channels/weixin-clawbot/users/{user_id}` | REST | Delete binding |
| `GET` | `/api/channels/sessions` | REST | List channel sessions |
| `PATCH` | `/api/channels/sessions/{session_id}` | REST | Update session reply mode |

## Usage Examples

### General Agent Q&A

```bash
curl -N -X POST http://localhost:7869/api/agent/general_api \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Summarize today'\''s work schedule for me",
    "session_id": "demo-session",
    "user_id": "demo-user",
    "internet_search": false,
    "deep_thinking": false
  }'
```

### Multimodal Agent Input

```bash
curl -N -X POST http://localhost:7869/api/agent/general_api \
  -H "Content-Type: application/json" \
  -d '{
    "query": [
      { "type": "text", "text": "What is in this image?" },
      {
        "type": "image",
        "url": "https://example.com/demo.jpg",
        "mime_type": "image/jpeg"
      }
    ],
    "session_id": "multi-modal-session",
    "user_id": "demo-user"
  }'
```

### Create Knowledge Base

```bash
curl -X POST http://localhost:7869/api/rag/knowledge-bases/create \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "demo-user",
    "name": "Product Documentation",
    "description": "Example knowledge base"
  }'
```

### Upload Document

```bash
curl -X POST http://localhost:7869/api/rag/knowledge-bases/documents/upload \
  -F "user_id=demo-user" \
  -F "knowledge_base_id=<knowledge_base_id>" \
  -F "files=@./demo.pdf"
```

### RAG Streaming Q&A

`index_name` and `graph_name` can be obtained from the knowledge base detail response's `passage_index` and `index_prefix`.

```bash
curl -N -X POST http://localhost:7869/api/rag/general_api \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What are the core conclusions of this document?",
    "session_id": "rag-session",
    "user_id": "demo-user",
    "index_name": "kb_xxx_passages",
    "graph_name": "kb_xxx"
  }'
```

## Configuration

### Required Environment Variables

| Variable | Description |
|----------|-------------|
| `OPENAI_API_BASE` | OpenAI-compatible LLM API endpoint |
| `OPENAI_API_KEY` | LLM API key |
| `CHAT_MODEL_NAME` | Chat model name |
| `EMBEDDING_MODEL_NAME` | Embedding model name |
| `ES_URL` | Elasticsearch URL |
| `ES_URSR` | Elasticsearch username |
| `ES_PWD` | Elasticsearch password |

### Common Optional Environment Variables

| Variable | Description |
|----------|-------------|
| `BACKEND_TYPE` | Execution backend: `local_shell` (default) / `store` / `sandbox` |
| `OPEN_SANDBOX_CODE_INTERPRETER_IMAGE` | Sandbox code interpreter image (default: `sandbox-registry.cn-zhangjiakou.cr.aliyuncs.com/opensandbox/code-interpreter:v1.0.2`) |
| `PG_DATABASE_URL` | Enable PostgresStore long-term memory |
| `TAVILY_API_KEY` | Enable web search tool |
| `USE_TOOL_SEARCH` | Enable deferred tool search |
| `USE_COPILOTKIT` | Enable CopilotKit middleware |
| `PHOENIX_COLLECTOR_ENDPOINT` | Enable Phoenix tracing |
| `AUTH_ADMIN_EMAIL` | Default admin email |
| `AUTH_ADMIN_PASSWORD` | Default admin password |
| `AUTH_TOKEN_EXPIRE_DAYS` | Login token validity (days) |
| `CHANNEL_AGENT_API_URL` | Channel gateway address for calling Agent |
| `WEIXIN_CLAWBOT_*` | WeChat ClawBot related configuration |

## Sandbox Mode (Multi-User Work Isolation)

When `BACKEND_TYPE=sandbox`, the system uses [OpenSandbox](https://github.com/opensandbox/opensandbox) to create an independent Docker container for each user as the execution environment, achieving multi-user work isolation.

### Isolation Mechanism

| Dimension | Description |
|-----------|-------------|
| Container Isolation | Each user has an independent OpenSandbox container; processes and filesystems are fully isolated |
| Workspace Isolation | Each user's workspace is mapped to `user_workspace/{user_id}/.deepclaw/` via Docker bind mount |
| Skill Directory Isolation | Private skill directories (`/.deepclaw/workspace/skills`) are mounted per-user, while shared skills (`/workspace/skills`) are common |
| Conversation History Isolation | Conversation history is written to each user's independent `conversation_history` directory |
| Lifecycle Management | After each agent execution, `OpenSandboxKillMiddleware` automatically terminates the user's sandbox and cleans up state |

### Execution Flow

1. On agent startup, `BACKEND_TYPE` is checked; if `sandbox`, the `OpenSandbox` backend is loaded
2. On first execution, `get_sandbox()` creates a new sandbox for the current `user_id` and persists the `sandbox_id` in the runtime store
3. Subsequent executions reuse the existing sandbox (reconnect via `sandbox_id`)
4. Supported sandbox operations: command execution (`execute`), file read/write (`write`/`read`), file editing (`edit`), file upload/download (`upload_files`/`download_files`)
5. After agent execution, `OpenSandboxKillMiddleware.after_agent` automatically terminates the sandbox and removes the store record

### Prerequisites

- Docker environment
- OpenSandbox Server running (see step 5 above)
- `.sandbox.toml` properly configured (example config provided in project root)
- Install the `opensandbox` extra dependency: `uv sync --dev --extra opensandbox`

### Configuration File `.sandbox.toml`

The `.sandbox.toml` file in the project root is the OpenSandbox Server configuration file. Key settings:

```toml
[server]
host = "127.0.0.1"
port = 8089

[runtime]
type = "docker"
execd_image = "docker.1ms.run/opensandbox/execd:v1.0.16"

[storage]
allowed_host_paths = ["/home/dev/liuyu/project/langchain-api"]
```

`allowed_host_paths` must include the project root directory, otherwise bind mounts will be rejected.

## Notes

- The backend serves `frontend/out` directly at `/`. If this directory exists, Node.js and pnpm are not needed for running.
- After modifying the frontend, you must re-run `pnpm build` for the backend to serve the latest pages.
- The default workspace is at `.deepclaw/workspace`.
- The channel module writes its SQLite database to `.deepclaw/channels.db` by default.
- If `frontend/out` does not exist, the backend still provides APIs, but `/` will not serve any frontend page.
- Sandbox mode (`BACKEND_TYPE=sandbox`) requires OpenSandbox Server to be running and `.sandbox.toml` to be properly configured (see the Sandbox Mode section above).

## License

Apache-2.0
