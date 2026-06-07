# DeepClaw

统一的智能体服务仓库，后端基于 FastAPI，集成了：

- 通用 Agent
- RAG 知识库
- 技能管理
- 飞书 / 钉钉 / 微信 ClawBot 渠道接入
- Next.js 前端静态托管

适合用来搭建企业知识问答、内部 Copilot、多工具智能体和渠道机器人。

## 核心能力

- `Agent`
  基于 LangGraph / DeepAgents，支持工具调用、SSE 流式响应、MCP 配置透传。

- `RAG`
  支持知识库创建、文档上传、切片查看、Graph RAG 检索和独立 RAG 问答。

- `Skills`
  支持技能列表、上传和删除。

- `Channels`
  内置飞书、钉钉、微信 ClawBot 路由、用户绑定和会话回复模式管理。

- `Frontend`
  Next.js 前端构建后由后端 `/` 统一托管。

## 项目结构

```text
deepclaw/
├── deepclaw/
│   ├── web_backend/         # FastAPI Web 应用层与所有 Web 功能目录
│   ├── agents/              # 通用 Agent / RAG Agent 组装、上下文与状态
│   ├── common/              # Elasticsearch、Graph RAG、文本切分等通用实现
│   ├── middleware/          # 业务开关、RAG 注入、MCP、工具搜索等中间件
│   ├── tools/               # 天气、网页抓取、检索、定时任务等工具
│   ├── backend/             # 执行后端相关实现
│   ├── patch/               # 第三方库补丁与适配
│   ├── main.py              # 兼容启动入口
│   └── settings.py          # 环境变量配置
├── frontend/                # Next.js 前端
├── .deepclaw/               # 运行时工作区、技能目录、渠道数据库等
├── assets/                  # 截图与静态资源
└── docker-compose.yml       # PostgreSQL / Elasticsearch / Phoenix
```

## 快速开始

### 1. 环境要求

- Python `>= 3.12`
- `uv`
- Docker / Docker Compose

如果需要开发或重新构建前端，还需要：

- Node.js `>= 18`
- `pnpm`

### 2. 启动依赖服务

```bash
docker-compose up -d postgresql elasticsearch
```

如需 Phoenix 观测：

```bash
docker-compose up -d phoenix
```

Phoenix 默认地址：`http://localhost:6006`

### 3. 初始化后端

```bash
cp .env.example .env
uv sync --dev
```

如需 OpenSandbox：

```bash
uv sync --dev --extra opensandbox
```

### 4. 配置 `.env`

至少填写：

```dotenv
OPENAI_API_KEY=your-api-key
OPENAI_API_BASE=http://localhost:8082/v1
CHAT_MODEL_NAME=qwen3
EMBEDDING_MODEL_NAME=qwen3-embedding
ES_URL=http://localhost:9200
ES_URSR=elastic
ES_PWD=elastic@2024
```

### 5. 启动后端

官方推荐入口：

```bash
uv run uvicorn deepclaw.web_backend.app:app --reload --host 0.0.0.0 --port 7869
```

启动后可访问：

- 前端页面：`http://localhost:7869/`
- Agent SSE：`POST /api/agent/general_api`
- Agent AG-UI：`POST /api/agent/ag_ui`
- RAG SSE：`POST /api/rag/general_api`
- Skills API：`/api/agent/skills/*`
- Knowledge Bases API：`/api/rag/knowledge-bases/*`
- Channels API：`/api/channels/*`

### 6. 前端开发

仅在需要开发或重新构建前端时执行：

```bash
cd frontend
pnpm install
pnpm dev
```

开发地址：`http://localhost:3000`

构建静态前端并交给后端托管：

```bash
cd frontend
pnpm build
```

## API 概览

### Agent

- `POST /api/agent/ag_ui`
- `POST /api/agent/general_api`
- `POST /api/agent/skills/list`
- `POST /api/agent/skills/upload`
- `POST /api/agent/skills/delete`

### RAG

- `POST /api/rag/general_api`
- `POST /api/rag/knowledge-bases/list`
- `POST /api/rag/knowledge-bases/create`
- `POST /api/rag/knowledge-bases/detail`
- `POST /api/rag/knowledge-bases/update`
- `POST /api/rag/knowledge-bases/delete`
- `POST /api/rag/knowledge-bases/bulk-delete`
- `POST /api/rag/knowledge-bases/documents/list`
- `POST /api/rag/knowledge-bases/documents/detail`
- `POST /api/rag/knowledge-bases/documents/upload`
- `POST /api/rag/knowledge-bases/documents/update`
- `POST /api/rag/knowledge-bases/documents/delete`
- `POST /api/rag/knowledge-bases/documents/bulk-delete`

### Channels

- `POST /api/channels/feishu/events`
- `POST /api/channels/dingtalk/events`
- `POST /api/channels/weixin-clawbot/qrcode`
- `GET /api/channels/weixin-clawbot/qrcode/status`
- `POST /api/channels/weixin-clawbot/users/{user_id}/qrcode`
- `GET /api/channels/weixin-clawbot/users`
- `DELETE /api/channels/weixin-clawbot/users/{user_id}`
- `GET /api/channels/sessions`
- `PATCH /api/channels/sessions/{session_id}`

## 配置说明

### 主服务环境变量

由 `deepclaw/settings.py` 读取：

- `OPENAI_API_BASE`
- `OPENAI_API_KEY`
- `CHAT_MODEL_NAME`
- `EMBEDDING_MODEL_NAME`
- `ES_URL`
- `ES_URSR`
- `ES_PWD`
- `TAVILY_API_KEY`
- `BACKEND_TYPE`
- `PG_DATABASE_URL`
- `LANGSMITH_API_KEY`
- `USE_COPILOTKIT`
- `USE_TOOL_SEARCH`
- `AUTH_ADMIN_EMAIL`
- `AUTH_ADMIN_PASSWORD`
- `AUTH_TOKEN_EXPIRE_DAYS`

### 渠道环境变量

由 `deepclaw/web_backend/channels/config.py` 读取：

- `CHANNEL_AGENT_API_URL`
- `WEIXIN_CLAWBOT_API_BASE_URL`
- `WEIXIN_CLAWBOT_PRINT_QRCODE_ON_STARTUP`
- `WEIXIN_CLAWBOT_AUTO_POLL_ON_STARTUP`
- `WEIXIN_CLAWBOT_LOGIN_POLL_INTERVAL_SECONDS`
- `WEIXIN_CLAWBOT_MESSAGE_POLL_INTERVAL_SECONDS`
- `WEIXIN_CLAWBOT_DEFAULT_REPLY_MODE`

### 可观测性

- `PHOENIX_COLLECTOR_ENDPOINT`

## 使用说明

- 后端会直接托管 `frontend/out`。如果该目录已存在，纯运行场景不需要安装 Node.js 和 pnpm。
- 前端修改后，必须重新执行 `pnpm build`，后端 `/` 才会提供最新页面。
- 默认工作区位于 `.deepclaw/workspace`。
- 渠道模块默认把 SQLite 数据库写入 `.deepclaw/channels.db`。
- 如果 `frontend/out` 不存在，后端仍可提供 API，但 `/` 不会挂载前端页面。

## License

Apache-2.0

