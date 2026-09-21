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
  - 在 `create_app()` 中挂载模块级 `auth`、`agui`、`channels`、`skills`、`knowledge_bases` 路由
  - 在应用生命周期中初始化 `AgentRegistry`
  - 提供 `/api/runtime-config` 运行时配置
  - 静态托管 `frontend/out`

- `deepclaw/web_backend/lifespan.py`
  应用生命周期入口。负责：
  - 可观测性初始化
  - `patch_langchain()`
  - 管理员账号自举
  - 渠道 runtime 生命周期接入

- `deepclaw/web_backend/db.py`
  Web 侧统一异步数据库辅助入口。负责：
  - 同步/异步数据库 URL 转换
  - `auth` / `channels` / `knowledge_bases` 默认元数据数据库选择
  - 当配置 `PG_DATABASE_URL` 时，优先落统一 PG；未配置时回退各自 SQLite

- `deepclaw/web_backend/common/agui_runs.py`
  AG-UI Run 公共执行逻辑、统一 Runs 路径解析、渠道 Agent URL 与 runtime-config 路由。
- `deepclaw/web_backend/common/agui_schemas.py`
  AG-UI HTTP 协议模型，当前包含 `AgUiRunRequest`、`RunSnapshotResponse`、`RunActionRequest` 与 Thread/Agent 响应模型。

- `deepclaw/agent_registry.py`
  统一 Agent 基类与自动发现入口。定义 `Agent` 与 `AgentRegistry`，扫描 `deepclaw.agents.*.agent` 模块并校验 `agent_id`、默认智能体和 `build_agent` 构建入口。
- `deepclaw/web_backend/agui/runtime.py`
  AG-UI 智能体运行时缓存，按应用和智能体缓存图与 Run 管理器。
- `deepclaw/web_backend/agui/router.py`
  模块级统一 AG-UI 路由器，提供 `/api/agui/agents`、`/api/agui/runs/*`、`/api/agui/threads/*`。

- `deepclaw/web_backend/agent/run_manager.py`
  基于 `RunStore` 的 Run 管理器，负责 Run 执行、`Last-Event-ID` 重放、恢复、取消与事件流编排。
- `deepclaw/web_backend/agent/run_store.py`
  Run/Thread 存储抽象层，定义 Thread owner、按 Thread 查询 Run、Run 状态、事件追加/重放、过期清理和订阅接口；当前提供 `InMemoryRunStore` 与 PostgreSQL/SQLite `SqlRunStore`，后续可新增 Redis 实现。

- `deepclaw/web_backend/common/errors.py`
  统一业务规则异常 `BusinessRuleError`，由 `create_app()` 注册的全局异常处理器转换为 `{"detail": ...}` 响应。

### Web 功能目录

- `deepclaw/web_backend/auth/`
  认证相关路由、请求模型、SQLModel、存储、服务与 FastAPI 依赖。

- `deepclaw/web_backend/channels/`
  渠道共享模型、会话存储、消息处理服务、共享会话接口与总装配入口。

- `deepclaw/web_backend/channels/feishu/`
  飞书渠道适配与事件路由。

- `deepclaw/web_backend/channels/dingtalk/`
  钉钉渠道适配与事件路由。

- `deepclaw/web_backend/channels/weixin_clawbot/`
  微信 ClawBot 专属适配器、API 客户端、运行时、生命周期、状态辅助与管理路由。

- `deepclaw/web_backend/skills/`
  技能管理路由、请求模型与服务实现。

- `deepclaw/web_backend/knowledge_bases/`
 知识库管理路由、请求模型、元数据存储与服务实现。

### 核心能力层

- `deepclaw/agents/general/`
  通用 Agent 组装、上下文、状态与运行时相关逻辑；`general/agent.py` 的 `GeneralAgent.build_agent` 直接承载构建实现。

- `deepclaw/agents/rag/`
  RAG Agent 组装、上下文与状态定义；`rag/agent.py` 的 `RagAgent.build_agent` 直接承载构建实现。

- `deepclaw/common/`
  Elasticsearch、向量数据库抽象、Graph RAG（`BaseGraphRAG` + `ElasticGraphRAG` + `PgGraphRAG`）、PDF 切分等通用算法实现。

- `deepclaw/common/vector_store/`
  向量数据库抽象层，包含通用 `AbstractVectorStore`、统一创建入口 `create_vector_store()`、Elasticsearch 实现，以及基于 PostgreSQL + pgvector + pg_search 的实现。

- `deepclaw/common/graph_rag/`
  Graph RAG 统一包，包含：
  - `base.py` — `BaseGraphRAG` 抽象基类，承载图构建、三元组抽取与 CRUD 编排的共享逻辑
  - `elastic.py` — `ElasticGraphRAG(BaseGraphRAG)`，Elasticsearch 专属的检索与写入
  - `pg.py` — `PgGraphRAG(BaseGraphRAG)`，PostgreSQL pgvector 版本，基于 `AbstractVectorStore` 接口实现应用层图遍历
  - `__init__.py` — 统一导出入口

- `deepclaw/common/elastic_graph_rag.py` / `deepclaw/common/pg_graph_rag.py`
  向后兼容的 re-export 存根，新代码请从 `deepclaw/common/graph_rag` 导入。

- `deepclaw/common/__init__.py`
  导出所有公共类型，并提供 `create_graph_rag()` 工厂函数，根据 `vector_store` 类型自动创建对应的 `ElasticGraphRAG` 或 `PgGraphRAG` 实例。

- `deepclaw/middleware/`
  业务开关、RAG 注入、MCP、工具搜索、计划，以及 `cron` 工具实现等中间件与运行时扩展。
  NL2SQL 相关逻辑在 `deepclaw/middleware/nl2sql/`，DDL 拉取采用可注册 fetcher 架构（`ddl/base.py` + 各数据库实现如 `ddl/pgsql.py`）。
  图表生成在 `deepclaw/middleware/chart/`，其中 `charts/` 是基于 matplotlib 的 9 种图表渲染引擎（bar/line/pie/column/scatter/area/histogram/funnel/radar）源码包，`ChartMiddleware` 负责 Agent 工具适配；核心渲染层无 langchain 依赖，可独立发布为 MCP Server。运行时图片固定输出到 `.deepclaw/workspace/charts/`，该目录仅存放生成文件并由 Git 忽略。
  `deepclaw/middleware/message_store.py`：MessageStoreMiddleware，直接写入 `thread_messages` 表；以 `thread_id` 为主键，并在 Agent 开始、模型调用前后、工具完成后和正常结束时覆盖保存完整 messages；内容未变化时不重复写库。

- `deepclaw/tools/`
  天气、网页抓取、检索等工具导出；`cron` 相关实现已归档到 `deepclaw/middleware/cron/`。
  `deepclaw/tools/ask_user.py`：基于 LangGraph `interrupt` 的人机协作提问工具；向客户端发送结构化问题载荷，并通过 `Command(resume=...)` 接收用户回答。

- `deepclaw/backend/`
  执行后端相关实现。

- `deepclaw/patch/`
  第三方库补丁与适配。

- `deepclaw/settings.py`
  主服务环境变量入口。

- `deepclaw/utils/`
  仓库级工具函数包。当前按主题拆分为：
  - `model_factory.py` — `get_chat_model()` / `get_embedding_model()`
  - `time_utils.py` — `get_current_time()`
  - `token_count.py` — 基于 `tiktoken` 与 `huggingface/tokenizers` 的 token 计数
  - `__init__.py` — 统一兼容导出入口，外部继续使用 `from deepclaw.utils import ...`

- `deepclaw/constant.py`
  定义：
  - `root_dir`
  - `home_path = .deepclaw`
  - `workspace_path = .deepclaw/workspace`

### 启动入口

- `deepclaw/main.py`
  当前对外统一从这里启动。修改启动装配逻辑时，优先改 `web_backend/app.py` 与 `web_backend/lifespan.py`。

### CLI 层

- `deepclaw/cli/main.py`
  Typer CLI 工具，提供 `deepclaw install` 命令一键安装运行依赖：
  - `deepclaw install playwright` — 安装 Playwright Chromium（含系统依赖）
  - `deepclaw install docker` — 拉取 sandbox Docker 镜像
  - `deepclaw install` — 同时执行 playwright 和 docker
  入口点注册在 `pyproject.toml` 的 `[project.scripts]` 中，`uv sync` 后可直接通过 `deepclaw` 命令调用。

## 启动与运行

### 后端

```bash
cp .env.example .env
uv sync --dev
uv run python -m deepclaw.main
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

- `HOST`
- `PORT`
- `LOCAL_HOST`
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
- `VECTOR_STORE_BACKEND`
- `LANGSMITH_API_KEY`
- `USE_COPILOTKIT`
- `USE_TOOL_SEARCH`
- `MCP_CONFIG`
- `AGUI_RUN_RETENTION_SECONDS`
- `AGUI_RUN_MAX_EVENTS`
- `AGUI_RUN_CLEANUP_INTERVAL_SECONDS`
- `AGUI_RUN_POLL_INTERVAL_SECONDS`
- `CHART_PUBLIC_URL`
- `CHART_RETENTION_HOURS`
- `CHART_MAX_FILES`
- `AUTH_ADMIN_EMAIL`
- `AUTH_ADMIN_PASSWORD`
- `AUTH_TOKEN_EXPIRE_DAYS`

### 渠道配置

`deepclaw/web_backend/channels/config.py` 当前识别：

- `CHANNEL_AGENT_API_URL`

`deepclaw/web_backend/channels/weixin_clawbot/settings.py` 当前识别：

- `WEIXIN_CLAWBOT_API_BASE_URL`
- `WEIXIN_CLAWBOT_PRINT_QRCODE_ON_STARTUP`
- `WEIXIN_CLAWBOT_AUTO_POLL_ON_STARTUP`
- `WEIXIN_CLAWBOT_LOGIN_POLL_INTERVAL_SECONDS`
- `WEIXIN_CLAWBOT_MESSAGE_POLL_INTERVAL_SECONDS`
- `WEIXIN_CLAWBOT_DEFAULT_REPLY_MODE`
- `WEIXIN_CLAWBOT_REQUEST_TIMEOUT_SECONDS`

### 可观测性

- `PHOENIX_COLLECTOR_ENDPOINT`

注意：`.env.example` 里可能有示例值或历史残留，修改配置逻辑时以实际代码为准。

## 必须要遵守的开发约束

- 所有新写的函数/方法都必须带中文 docstring（功能说明 + Args 每行）。禁止 `"""...""" ...` 同行。
- 所有 schema 类名必须通过后缀区分请求与响应：请求模型以 `Request` 结尾，响应模型以 `Response` 结尾；嵌套响应模型也必须遵守该规则。
- Python 字段、变量、参数和函数名统一使用 `snake_case`；对外 JSON 需要 `camelCase` 时通过 Pydantic alias 映射，不直接把 Python 字段命名为 camelCase。
- 只改任务直接相关的代码，不做顺手重构。
- Python 导入统一使用 `deepclaw.*` 绝对导入，禁止使用 `from .`、`from ..` 等相对导入。
- 包结构调整后同步更新本文档的「当前代码结构」。
- `deepclaw/agents/` 只放 Agent 实现与对应的 `Agent` 子类；Agent 自动发现和注册基础设施放在 `deepclaw/agent_registry.py`。
- 未经用户明确要求，不要执行 `git add`、`git commit`、`git amend`。
- 测试统一使用 `pytest`，不要引入 `unittest` 风格测试。
- 不要新增仅校验日志输出内容的测试用例；日志无需专门测试。
- 如果成熟、稳定、维护活跃的开源库能更好解决问题，优先采用开源库方案。
- 当前 Web 目录已经统一收口到 `web_backend`，不要再新增新的根包 `auth`、`channels`、`management`、`api` 目录。
- 如果修改会影响静态托管行为，记得同时检查 `frontend/out` 是否需要重新构建。
- 所有数据库操作必须使用 SQLModel 的原生异步功能：`async_sessionmaker` 用 `class_=AsyncSession`（`from sqlmodel.ext.asyncio.session import AsyncSession`），查询用 `await session.exec(select(...))`（`select` 从 `sqlmodel` 导入而非 `sqlalchemy`），结果直接用 `.one()/.first()/.all()` 获取模型实例（不使用 `.scalars()`），写入用 `session.add()` + `commit()` + `refresh()`。
- 输出文档必须是中文。
- 如果代码结构变化，必须同步更新 `AGENTS.md`。
- 代码更改后，必须执行 `codegraph sync` 更新索引。
- 代码修改完成后，必须运行 pytest 测试进行验证：`uv run pytest` 使用 `-q -n auto` 并行执行测试。

## 最小验证

修改 Python 文件后，至少运行 Ruff：

```bash
uv run ruff check .
```

如果本次任务涉及测试补充或测试修改，使用 `pytest` 执行相关测试，例如：

```bash
uv run pytest tests -q -n auto
```

修改前端文件后，至少运行：

```bash
cd frontend
pnpm lint
pnpm build
```

只改文档时，不需要额外构建，但必须基于最新代码核对：

- 路由前缀是否真实存在
- 环境变量名是否与 `settings.py` / `web_backend/channels/config.py` / `web_backend/channels/weixin_clawbot/settings.py` 一致
- 前端托管路径是否仍为 `/`
- 工作区路径是否仍为 `.deepclaw/workspace`

## 当前公开接口事实

- 主入口挂载统一 `agui` 路由，以及 `channels`、技能、知识库等业务路由
- 主入口还挂载 `/api/auth/*` 登录鉴权接口
- 浏览器与渠道统一走 AG-UI Runs：
  - 智能体列表：`GET /api/agui/agents`
  - 创建 Run：`POST /api/agui/runs`，通过顶层 `agentId` 选择通用 Agent 或 RAG Agent
  - 续流/重放：`GET /api/agui/runs/{run_id}/events`
  - 恢复：`POST /api/agui/runs/{run_id}/resume`
  - 取消：`POST /api/agui/runs/{run_id}/cancel`
- 新增 Agent 时只需在 `deepclaw/agents/<name>/agent.py` 中定义 `Agent` 子类，`AgentRegistry.discover()` 会自动加载；不需要修改 Web 路由或集中式 Agent 列表。
- 运行参数（`user_id`、`internet_search`、`deep_thinking`、`mcp_config`、`index_name`、`graph_name`、`header_info`）统一存放在 LangGraph state，不再依赖独立 context 模型
- Thread 资源现在记录 `thread_id -> owner_user_id + agent_id`，创建 Run 时会自动创建或校验 Thread 归属
- Thread 接口：`GET /api/agui/threads`、`GET /api/agui/threads/{thread_id}/runs`、`GET /api/agui/threads/{thread_id}/state`、`DELETE /api/agui/threads/{thread_id}`
- 旧的 `/api/agent/get_session_list`、`/api/agent/delete_session`、`/api/agent/get_state` 已移除，统一使用 Thread API。
- 技能管理归属 `/api/agent/skills/*`
- 知识库管理归属 `/api/rag/knowledge-bases/*`
- 渠道管理归属 `/api/channels/*`
- 前端默认以游客模式进入，点击右上角头像会跳转到独立 `/login` 页面进入登录/注册流程
- `auth`、`channels`、`knowledge_bases` 元数据默认优先使用 `PG_DATABASE_URL`；未配置时各自回退到 `.deepclaw` 下的 SQLite，并在默认初始化路径上兼容导入历史 SQLite 数据

## 文档协作原则

- `README.md` 面向中文外部使用者，优先写“怎么跑、怎么调、有哪些公开能力”。
- `README_EN.md` 是 `README.md` 的英文翻译，保持内容同步；修改中文版后应同步更新英文版。
- `AGENTS.md` 面向仓库协作方，优先写“代码怎么组织、改哪里、怎么验证、有哪些边界”。
- 三份文档职责分开，避免互相复制导致失真。
## 2026-06 Channels 补充事实

- `deepclaw/web_backend/channels/models.py` 现在新增统一的 `ChannelBinding` 模型，用来承载多用户 IM 绑定的凭据、配置和运行态。
- `deepclaw/web_backend/channels/store.py` 现在同时负责 `ChannelBinding` 的 CRUD；新渠道优先复用 `upsert_binding()`，不要重复造绑定存储。
- `deepclaw/web_backend/channels/runtime_manager.py` 是统一 runtime task 管理入口；长连接或轮询型渠道优先接这里。
- `deepclaw/web_backend/channels/feishu/` 现在已包含 `settings.py`、`client.py`、`adapter.py`、`runtime.py`、`router.py`，并以多用户 long connection 为主。
- `deepclaw/web_backend/channels/weixin_clawbot/` 仍保留二维码登录和轮询实现，但绑定信息会同步写入统一 `ChannelBinding`，后续扩展应优先面向 binding。
- `deepclaw/web_backend/channels/weixin_clawbot/lifespan.py` 现在会在应用启动时一并拉起已保存的 Feishu runtime 与 Weixin runtime。
- 渠道层的多用户边界现在以 `binding_id` 为核心；涉及会话隔离时必须把 binding 维度带上，避免不同绑定实例复用同一条渠道会话。
## 2026-06-10 IM 绑定中心补充事实

- `deepclaw/web_backend/channels/store.py` 现在同时支持 `create_binding()`、`update_binding()`、`list_bindings()`、`delete_binding()`；新代码不要再把“每个用户每个渠道只能有一个绑定”写死。
- `deepclaw/web_backend/channels/bindings_router.py` 提供统一的 `/api/channels/bindings` 列表接口；普通用户默认看自己的绑定，管理员可切 `scope=all` 查看全量绑定。
- `deepclaw/web_backend/channels/feishu/router.py` 现在同时保留旧的 `/feishu/users/{user_id}/binding` 兼容路径，并新增 `/feishu/bindings` 与 `/feishu/bindings/{binding_id}` 多绑定接口。
- `deepclaw/web_backend/channels/weixin_clawbot/router.py` 现在同时保留旧的 `user_id` 兼容路径，并新增：
  - `/weixin-clawbot/bindings`
  - `/weixin-clawbot/bindings/{binding_id}/qrcode`
  - `/weixin-clawbot/bindings/{binding_id}/qrcode/status`
  - `/weixin-clawbot/bindings/{binding_id}`
- `deepclaw/web_backend/channels/weixin_clawbot/runtime.py` 与 `deepclaw/web_backend/channels/weixin_clawbot/lifespan.py` 现在支持按 `binding_id` 启停 runtime；同一系统用户下的多个微信绑定不能复用同一个 runtime 或同一条渠道会话。
- 前端 [frontend/components/chat-interface/ChannelManagementView.tsx](/e:/git_dir/langchain-api/frontend/components/chat-interface/ChannelManagementView.tsx) 已从“单微信扫码管理页”升级为统一绑定中心，包含：
  - `我的绑定`
  - `管理员总览`
  - 微信多绑定管理
  - 飞书多绑定管理
