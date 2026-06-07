# AGENTS.md

本文档面向仓库协作代理与开发者，记录当前仓库的真实结构、改动边界与最小验证要求。`README.md` 面向外部使用者，这里不重复写外部上手说明。

## 项目定位

这是一个统一的智能体服务仓库，后端通过 FastAPI 暴露三类能力：

- `Agent`：通用智能体、工具调用、MCP 配置、技能管理
- `RAG`：知识库管理、图检索和独立 RAG 问答
- `Channels`：飞书、钉钉、微信 ClawBot 渠道接入与会话管理

前端是一个独立的 Next.js 应用，构建后由后端静态托管。

## 当前代码结构

### Web 应用层

- `deepclaw/web_backend/app.py`
  当前 FastAPI 官方装配入口。负责：
  - 创建 `FastAPI` 应用
  - 初始化 checkpointer 与 store
  - 挂载 `auth`、`agent`、`rag`、`channels`、`skills`、`knowledge_bases` 路由
  - 静态托管 `frontend/out`

- `deepclaw/web_backend/lifespan.py`
  应用生命周期入口。负责：
  - 可观测性初始化
  - `patch_langchain()`
  - 管理员账号自举
  - 渠道 runtime 生命周期接入

- `deepclaw/web_backend/common/endpoints.py`
  通用 SSE 端点封装。当前 `query` 支持：
  - 字符串
  - 结构化多模态数组：`text` / `image`

### Web 功能目录

- `deepclaw/web_backend/auth/`
  认证相关路由、请求模型、SQLModel、存储、服务与 FastAPI 依赖。

- `deepclaw/web_backend/channels/`
  渠道路由、适配器、运行时存储、会话服务、微信 runtime 生命周期与配置。

- `deepclaw/web_backend/skills/`
  技能管理路由、请求模型与服务实现。

- `deepclaw/web_backend/knowledge_bases/`
  知识库管理路由、请求模型与服务实现。

- `deepclaw/web_backend/agent/router.py`
  Agent 的 AG-UI 与通用 SSE HTTP 入口。

- `deepclaw/web_backend/rag/router.py`
  RAG 的通用 SSE HTTP 入口。

### 核心能力层

- `deepclaw/agents/general/`
  通用 Agent 组装、上下文、状态与运行时相关逻辑。

- `deepclaw/agents/rag/`
  RAG Agent 组装、上下文与状态定义。

- `deepclaw/common/`
  Elasticsearch、Graph RAG、PDF 切分等通用算法实现。

- `deepclaw/middleware/`
  业务开关、RAG 注入、MCP、工具搜索、计划等中间件。

- `deepclaw/tools/`
  天气、网页抓取、检索、定时任务等工具。

- `deepclaw/backend/`
  执行后端相关实现。

- `deepclaw/patch/`
  第三方库补丁与适配。

- `deepclaw/settings.py`
  主服务环境变量入口。

- `deepclaw/constant.py`
  定义：
  - `root_dir`
  - `home_path = .deepclaw`
  - `workspace_path = .deepclaw/workspace`

### 兼容入口

- `deepclaw/main.py`
  当前仍可直接启动，但官方推荐入口已切换到 `deepclaw.web_backend.app:app`。修改启动装配逻辑时，优先改 `web_backend/app.py` 与 `web_backend/lifespan.py`。

## 启动与运行

### 后端

```bash
cp .env.example .env
uv sync --dev
uv run uvicorn deepclaw.web_backend.app:app --reload --host 0.0.0.0 --port 7869
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

`deepclaw/settings.py` 当前识别：

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

### 渠道配置

`deepclaw/web_backend/channels/config.py` 当前识别：

- `CHANNEL_AGENT_API_URL`
- `WEIXIN_CLAWBOT_API_BASE_URL`
- `WEIXIN_CLAWBOT_PRINT_QRCODE_ON_STARTUP`
- `WEIXIN_CLAWBOT_AUTO_POLL_ON_STARTUP`
- `WEIXIN_CLAWBOT_LOGIN_POLL_INTERVAL_SECONDS`
- `WEIXIN_CLAWBOT_MESSAGE_POLL_INTERVAL_SECONDS`
- `WEIXIN_CLAWBOT_DEFAULT_REPLY_MODE`

### 可观测性

- `PHOENIX_COLLECTOR_ENDPOINT`

注意：`.env.example` 里可能有示例值或历史残留，修改配置逻辑时以实际代码为准。

## 开发约束

- 只改与当前任务直接相关的代码，避免顺手重构。
- 保持最小改动，优先修根因，不要扩散影响面。
- 目录重构时优先执行移动，再做最小导包修复。
- 关键逻辑补充必要的中文注释，避免无意义注释。
- 未经用户明确要求，不要执行 `git add`、`git commit`、`git amend`。
- 测试统一使用 `pytest`，不要引入 `unittest` 风格测试。
- 如果成熟、稳定、维护活跃的开源库能更好解决问题，优先采用开源库方案。
- 当前 Web 目录已经统一收口到 `web_backend`，不要再新增新的根包 `auth`、`channels`、`management`、`api` 目录。
- 如果修改会影响静态托管行为，记得同时检查 `frontend/out` 是否需要重新构建。
- 输出文档必须是中文。
- 如果代码结构变化，必须同步更新 `AGENTS.md`。
- 代码更改后，必须执行 `codegraph index --force` 更新索引。

## 最小验证

修改 Python 文件后，至少运行：

```bash
uv run python -m py_compile <changed_file.py>
```

代码修改后，还必须运行 Ruff：

```bash
uv run ruff check .
```

如果本次任务涉及测试补充或测试修改，使用 `pytest` 执行相关测试，例如：

```bash
uv run pytest tests -q
```

修改前端文件后，至少运行：

```bash
cd frontend
pnpm lint
pnpm build
```

只改文档时，不需要额外构建，但必须基于最新代码核对：

- 路由前缀是否真实存在
- 环境变量名是否与 `settings.py` / `web_backend/channels/config.py` 一致
- 前端托管路径是否仍为 `/`
- 工作区路径是否仍为 `.deepclaw/workspace`

## 当前公开接口事实

- 主入口同时挂载 `agent`、`rag`、`channels`
- 主入口还挂载 `/api/auth/*` 登录鉴权接口
- 通用 SSE 接口支持多模态 `query`
- 技能管理归属 `/api/agent/skills/*`
- 知识库管理归属 `/api/rag/knowledge-bases/*`
- 渠道管理归属 `/api/channels/*`
- 前端默认以游客模式进入，点击右上角头像会跳转到独立 `/login` 页面进入登录/注册流程
- 渠道会话默认写本地 SQLite，而不是 Elasticsearch 或 Postgres

## 文档协作原则

- `README.md` 面向外部使用者，优先写“怎么跑、怎么调、有哪些公开能力”。
- `AGENTS.md` 面向仓库协作方，优先写“代码怎么组织、改哪里、怎么验证、有哪些边界”。
- 两份文档职责分开，避免互相复制导致失真。

