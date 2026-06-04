# AGENTS.md

本文件面向协作代理和开发者，描述当前仓库的真实结构、入口、边界和最小验证要求。`README.md` 面向外部使用者；这里不重复写外部上手说明，而是聚焦工程协作。

## 项目定位

这是一个统一的智能体服务仓库，后端通过 FastAPI 暴露三类能力：

- `Agent`：通用智能体、工具调用、MCP 配置、技能管理
- `RAG`：知识库管理、图检索和独立 RAG 问答
- `Channels`：飞书、钉钉、微信 ClawBot 渠道接入与会话管理

前端是一个独立的 Next.js 应用，构建后由后端静态托管。

## 代码结构

### 后端主包

- `langchain_api/main.py`
  FastAPI 唯一启动入口。负责：
  - 创建 `FastAPI` 应用
  - 初始化 checkpointer 和 store
  - 挂载 `agent`、`rag`、`channels` 三套路由
  - 注册生命周期逻辑和前端静态文件

- `langchain_api/settings.py`
  主服务环境变量入口，管理模型、Elasticsearch、后端类型、工具搜索、CopilotKit、Phoenix 等配置。

- `langchain_api/constant.py`
  定义：
  - `root_dir`
  - `home_path = .langchain_api`
  - `workspace_path = .langchain_api/workspace`

### Agent 相关

- `langchain_api/agent/agent.py`
  通用 Agent 组装入口。默认走 DeepAgent，按配置接入：
  - `BusinessMiddleware`
  - `MCPMiddleware`
  - `DeferredToolMiddleware`
  - `local_shell` / `store` / `sandbox` 后端

- `langchain_api/agent/context.py`
  通用 Agent 请求上下文，包含：
  - `user_id`
  - `internet_search`
  - `deep_thinking`
  - `mcp_config`

- `langchain_api/agent/skill_manager.py`
  技能文件管理逻辑，供技能管理接口调用。

### RAG 相关

- `langchain_api/rag/agent.py`
  RAG Agent 组装入口，主要接入 `RAGMiddleware` 和 `BusinessMiddleware`。

- `langchain_api/rag/knowledge_base.py`
  知识库管理核心实现，负责知识库元数据、文档元数据、文档上传、切片查询和删除。

- `langchain_api/rag/retriever.py`
  检索入口，衔接 ES 检索与 Graph RAG。

- `langchain_api/rag/elastic_graph_rag.py`
  图检索核心实现，负责 passage / entity / relation 三类索引协同。

- `langchain_api/rag/text_splitter.py`
  PDF 解析与切分逻辑。

### API 层

- `langchain_api/api/endpoints.py`
  通用 SSE 端点封装。
  当前 `query` 支持：
  - 字符串
  - 结构化多模态数组：`text` / `image`

- `langchain_api/api/routers/agent.py`
  注册：
  - `/api/agent/ag_ui`
  - `/api/agent/general_api`
  - `/api/agent/skills/*`

- `langchain_api/api/routers/rag.py`
  注册：
  - `/api/rag/general_api`
  - `/api/rag/knowledge-bases/*`

- `langchain_api/api/routers/channels.py`
  注册：
  - `/api/channels/feishu/events`
  - `/api/channels/dingtalk/events`
  - `/api/channels/weixin-clawbot/*`
  - `/api/channels/sessions`

- `langchain_api/api/management/skills.py`
  技能列表、上传、删除接口。

- `langchain_api/api/management/knowledge_bases.py`
  知识库和文档管理接口。

### Channels 相关

- `langchain_api/channels/config.py`
  渠道配置入口，管理：
  - `CHANNEL_AGENT_API_URL`
  - `WEIXIN_CLAWBOT_*`

- `langchain_api/channels/service.py`
  渠道消息处理主流程。

- `langchain_api/channels/agent_client.py`
  渠道侧调用 Agent 通用接口的客户端。

- `langchain_api/channels/store.py`
  渠道运行时存储，默认写入 `.langchain_api/channels.db`。

- `langchain_api/channels/lifespan.py`
  服务生命周期内恢复和管理微信 ClawBot runtime。

- `langchain_api/channels/adapters/`
  渠道适配层，当前有：
  - `feishu.py`
  - `dingtalk.py`
  - `weixin_clawbot.py`

### 中间件 / 工具 / 前端

- `langchain_api/middleware/`
  包含业务开关、RAG 注入、MCP、工具搜索、计划等中间件。

- `langchain_api/tools/`
  当前内置天气、网页抓取和定时任务相关工具。

- `frontend/`
  Next.js 前端源码。主要视图包括：
  - 聊天
  - 知识库
  - 技能管理
  - MCP 管理
  - 渠道管理
  - 用户管理

## 启动与运行

### 后端

```bash
cp .env.example .env
uv sync --dev
uv run uvicorn langchain_api.main:app --reload --host 0.0.0.0 --port 7869
```

### 前端

```bash
cd frontend
pnpm install
pnpm dev
pnpm build
```

注意：

- 开发态前端地址是 `http://localhost:3000`
- 后端 `/` 只会托管 `frontend/out`
- 修改前端后如果要通过后端访问，必须重新 `pnpm build`

## 环境变量边界

### 主服务配置

`langchain_api/settings.py` 当前识别：

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

### 渠道配置

`langchain_api/channels/config.py` 当前识别：

- `CHANNEL_AGENT_API_URL`
- `WEIXIN_CLAWBOT_API_BASE_URL`
- `WEIXIN_CLAWBOT_PRINT_QRCODE_ON_STARTUP`
- `WEIXIN_CLAWBOT_AUTO_POLL_ON_STARTUP`
- `WEIXIN_CLAWBOT_LOGIN_POLL_INTERVAL_SECONDS`
- `WEIXIN_CLAWBOT_MESSAGE_POLL_INTERVAL_SECONDS`
- `WEIXIN_CLAWBOT_DEFAULT_REPLY_MODE`

### 可观测性

- `PHOENIX_COLLECTOR_ENDPOINT`

注意：`.env.example` 里有一些示例值和重复项，修改配置逻辑时以实际代码为准，不要只参考示例文件。

## 开发约束

- 只改和当前任务直接相关的代码，避免顺手重构。
- 保持最小改动，优先修根因，不要扩散影响面。
- 现有仓库没有统一测试框架配置，不要为了当前任务临时引入新测试体系。
- 前端和后端都有对外接口时，先确认真实入口挂载位置，再写文档或改前端调用。
- 如果修改会影响静态托管行为，记得同时检查 `frontend/out` 是否需要重新构建。

## 最小验证

修改 Python 文件后，至少运行：

```bash
uv run python -m py_compile <changed_file.py>
```

修改前端文件后，至少运行：

```bash
cd frontend
pnpm lint
pnpm build
```

只改文档时，不需要额外构建，但必须基于最新代码核对：

- 路由前缀是否真实存在
- 环境变量名是否与 `settings.py` / `channels/config.py` 一致
- 前端托管路径是否仍为 `/`
- 工作区路径是否仍为 `.langchain_api/workspace`

## 当前公开接口事实

- 主入口同时挂载 `agent`、`rag`、`channels`
- 通用 SSE 接口支持多模态 `query`
- 技能管理归属 `/api/agent/skills/*`
- 知识库管理归属 `/api/rag/knowledge-bases/*`
- 渠道管理归属 `/api/channels/*`
- 渠道会话默认写本地 SQLite，而不是 Elasticsearch 或 Postgres

## 文档协作原则

- `README.md` 面向外部使用者，优先写“怎么跑、怎么调、有哪些公开能力”。
- `AGENTS.md` 面向仓库协作方，优先写“代码怎么组织、改哪里、怎么验证、有哪些边界”。
- 两份文档职责分开，避免互相复制导致失真。
