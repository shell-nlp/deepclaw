<p align="right">
  <strong>🇨🇳 中文</strong> | <a href="README_EN.md">🇬🇧 English</a>
</p>

<p align="center">
  <img src="assets/img/logo.png" alt="DeepClaw" width="360">
</p>

<p align="center">
  <strong>开箱可用的企业级智能体工作台</strong><br>
  一个 FastAPI 进程同时提供 AG-UI 运行时、知识库、技能、渠道接入与前端界面
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
  <a href="#快速开始">快速开始</a>
  ·
  <a href="#核心能力">核心能力</a>
  ·
  <a href="#界面预览">界面预览</a>
  ·
  <a href="#api-接口">API 接口</a>
  ·
  <a href="#配置说明">配置说明</a>
  ·
  <a href="#项目结构">项目结构</a>
</p>

DeepClaw 把「智能体运行时」和「周边工程」收敛成一个可直接部署的服务：浏览器与 IM 渠道走同一套
AG-UI 运行协议，通用智能体与 RAG 智能体通过同一个 `agentId` 切换，会话状态由 LangGraph
checkpoint 统一持久化，前端构建产物由同一个进程静态托管。

适合这些场景：

- 需要一套统一入口来承载多个业务智能体（通用助手、知识库问答、后续自定义 Agent）。
- 需要把智能体接入飞书 / 钉钉 / 微信等内部渠道，并支持一个用户维护多条绑定。
- 需要在工具调用前插入人工审批，或让智能体在关键节点向用户追问。
- 需要私有化部署：模型走任意 OpenAI 兼容网关，状态落自己的 PostgreSQL。

## 核心能力

| 能力 | 说明 |
|------|------|
| 统一 AG-UI 运行时 | 浏览器与渠道都调用 `/api/agui/runs`，顶层 `agentId` 选择智能体，SSE 流式返回并支持 `Last-Event-ID` 断线重放 |
| 多智能体自动发现 | 新增智能体只需在 `deepclaw/agents/<name>/agent.py` 定义 `Agent` 子类，注册表自动加载，无需改路由 |
| 会话与状态 | Thread 归属、Run 记录、事件缓存、图状态统一由 LangGraph checkpoint + PostgreSQL 持久化，多实例可共享 |
| 通用 Agent | 基于 LangGraph / DeepAgents 构建，内置天气、网页抓取、检索等工具，支持 MCP 配置与技能包扩展 |
| RAG 知识库 | 知识库创建、文档上传、切片查看、图检索，以及独立的 RAG 智能体问答 |
| 多模态输入 | AG-UI `messages` 支持文本与图片等混合内容块，由适配层转换后交给模型 |
| 人机协作（HITL） | 工具调用前可配置审批，支持批准 / 编辑 / 拒绝；中断通过 `RUN_FINISHED.outcome` 暴露，恢复走标准 `resume[]` |
| 技能管理 | 技能列表、上传与删除，技能包以 zip 形式落到工作区技能目录 |
| 渠道接入 | 内置飞书、钉钉、微信 ClawBot 接入，统一以「绑定（binding）」为多用户边界 |
| 图表工具 | 内置 9 种 matplotlib 图表渲染，可配置公网前缀，生成结果由服务直接对外提供 |
| 定时任务（可选） | `CronMiddleware` 提供 Agent 可调用的定时任务增删查能力，默认 Agent 未启用，需要时显式接入 |
| 认证与游客模式 | 不透明访问令牌（`sha256` 入库、可即时撤销）与管理员/普通用户角色；未登录自动降级为游客身份 |
| 多执行后端 | 支持 `local_shell`、`store`、`sandbox` 三种执行模式 |
| 多用户沙箱隔离 | `sandbox` 模式下每个用户拥有独立的 OpenSandbox 容器，工作区与会话历史隔离，公共技能/记忆可按配置共享 |
| 前端界面 | Next.js + React 聊天 UI，构建后由 FastAPI 的 `/` 统一托管 |
| 可观测性 | 可选接入 Phoenix tracing、Postgres 长期记忆和 Tavily 搜索 |

## 界面预览

以下界面覆盖项目的主要工作流：聊天与流式工具调用、人工确认、知识库、技能管理、MCP 管理、
渠道绑定中心与用户管理。截图位于 `assets/img/`，更新界面后可自行替换。

### 聊天主界面

![聊天界面](assets/img/chat.png)

统一承载 Agent 对话、工具调用流式输出和核心交互入口。

### Human in the Loop 人工确认

![Human in the Loop](assets/img/human_in_the_loop.png)

展示工具调用进入人工确认后的审批与参数编辑流程。

### 知识库管理

![知识库管理](assets/img/knowledge_base.png)

用于查看知识库列表、知识详情、文档分页和切片明细。

### 技能管理

![技能管理](assets/img/skill_management.png)

用于上传、删除和维护工作区技能目录。

### MCP 管理

![MCP 管理](assets/img/mcp_management.png)

用于维护 MCP 配置，并控制通用 Agent 请求是否附带 MCP 服务定义。

### 渠道管理

![渠道管理](assets/img/channels_management.png)

统一的渠道绑定中心：同一用户可维护多条飞书 / 微信绑定，每条绑定独立二维码、独立状态、独立删除。

### 用户管理

![用户管理](assets/img/user_management.png)

管理员可创建用户、调整角色、启用停用与重置密码；停用或重置密码会即时撤销该用户全部登录令牌。

## 技术栈

| 模块 | 技术 |
|------|------|
| Web 框架 | FastAPI + Uvicorn |
| 智能体 | LangGraph, LangChain, DeepAgents, ag-ui-langgraph |
| 协议 | AG-UI（HTTP + SSE） |
| RAG | PostgreSQL + pgvector + pg_search，或 Elasticsearch（Dense Vector + BM25）；Graph RAG 支持 Elasticsearch / PostgreSQL，Graph DB 支持 Neo4j / NetworkX |
| 状态存储 | LangGraph checkpoint（PostgreSQL / 内存）、Run/Thread 事件表（PostgreSQL / SQLite / 内存）、AsyncPostgresStore / InMemoryStore |
| 前端 | Next.js 15, React 19, TypeScript, CSS Modules |
| 执行后端 | Local Shell, Store Backend, OpenSandbox（Docker 容器沙箱） |
| 认证 | 不透明访问令牌（`hashlib.scrypt` 密码哈希 + SHA-256 令牌哈希） |
| 可选组件 | Phoenix, Tavily, OpenSandbox Server |
| 包管理 | uv, pnpm |

## 项目结构

```text
deepclaw/
├── deepclaw/
│   ├── agent_registry.py    # Agent 基类与自动发现注册表
│   ├── agents/              # 智能体实现：general/ 通用智能体、rag/ 知识库智能体
│   ├── common/              # 向量库、Graph DB / Graph RAG、Docling 解析与文本切分
│   ├── middleware/          # 业务开关、MCP、图表、NL2SQL、记忆、Python 执行、沙箱等
│   ├── patch/               # 第三方库补丁与适配
│   ├── sandbox/             # OpenSandbox 执行后端
│   ├── tools/               # 天气、网页抓取、检索、ask_user 等工具
│   ├── utils/               # 模型工厂、时间工具、token 计数
│   ├── web_backend/         # FastAPI 应用层：agui / agent / auth / channels / common / skills / knowledge_bases
│   ├── constant.py          # 路径等模块级常量
│   ├── main.py              # 主启动入口
│   └── settings.py          # 环境变量配置
├── frontend/                # Next.js 前端（app/ 源码，out/ 为构建产物，由后端静态托管）
├── mcp2tool/                # FastMCP 转 LangChain 工具适配
├── docker/                  # PostgreSQL 等中间件镜像构建文件
├── assets/                  # README 图标与界面截图
├── docs/                    # 设计文档与历史归档
├── tests/                   # pytest 测试
├── .deepclaw/               # 运行时工作区：技能、图表、上传文件、SQLite 回退库
├── user_workspace/          # 用户工作区目录（sandbox 模式每用户独立子目录）
├── .env.example             # 环境变量示例（不要提交 .env）
├── .sandbox.toml            # OpenSandbox Server 配置（sandbox 模式必需）
├── docker-compose.middleware.yml  # 中间件：PostgreSQL / Elasticsearch / Phoenix / Neo4j
├── docker-compose.app.yml         # 应用：deepclaw 主服务
├── Dockerfile                     # 主服务镜像
├── Dockerfile.code-interpreter-rebuild  # OpenSandbox 代码解释器镜像重建
└── pyproject.toml                 # 依赖与可选 extras 定义
```

> 前端组件已按业务域拆到 `frontend/components/chat/`；旧的 `frontend/components/chat-interface/` 仍在逐步迁移。

## 系统架构

```text
浏览器  ·  飞书  ·  钉钉  ·  微信 ClawBot
                    │
                    ▼
        POST /api/agui/runs          统一 AG-UI 入口，顶层 agentId 选择智能体
        GET  /api/agui/agents        可用智能体列表
                    │
                    ▼
┌───────────────────────────────────────────────────────────────────┐
│ FastAPI 应用层（deepclaw/web_backend）                             │
│                                                                   │
│   /api/auth/*       认证：注册、登录、退出、用户与角色管理            │
│   /api/agui/*       AG-UI：Run、Thread、SSE 事件流与重放            │
│   /api/agent/*      技能管理                                       │
│   /api/rag/*        知识库与文档管理                                │
│   /api/channels/*   渠道绑定与会话                                  │
│   /api/runtime-config  前端运行时路径配置                           │
└───────────────────────────────────────────────────────────────────┘
                    │
                    ▼
┌───────────────────────────────────────────────────────────────────┐
│ Agent 运行时                                                       │
│                                                                   │
│   AgentRegistry 自动发现 → AgentRuntimeCache 按智能体缓存图与管理器   │
│     ├─ agent   通用智能体：工具 / MCP / 技能 / 图表 / HITL / 计划     │
│     └─ rag     知识库智能体：RAGMiddleware 检索与重写                │
│                                                                   │
│   LangGraph checkpoint + store 承载会话状态、长期记忆与消息时间        │
└───────────────────────────────────────────────────────────────────┘
                    │
                    ▼
┌───────────────────────────────────────────────────────────────────┐
│ 基础设施                                                           │
│                                                                   │
│   PostgreSQL      状态、事件、元数据、pgvector 向量（可选统一存储）    │
│   Elasticsearch   向量 + 关键词检索（VECTOR_STORE_BACKEND 切换）     │
│   SQLite          未配置 PostgreSQL 时的回退存储                     │
│   Docker          OpenSandbox 沙箱容器（BACKEND_TYPE=sandbox）       │
│   LLM 网关         任意 OpenAI 兼容接口                             │
│   Phoenix         分布式追踪（可选）                                 │
└───────────────────────────────────────────────────────────────────┘
```

## 快速开始

### 1. 环境要求

| 场景 | 依赖 |
|------|------|
| 仅运行后端和已构建前端 | Python `>= 3.12`、`uv`、Docker / Docker Compose |
| 开发或重新构建前端 | 额外需要 Node.js `>= 18`、`pnpm` |

如果仓库里的 `frontend/out` 已经存在，且你不修改前端代码，可以直接跳过前端安装和构建步骤。

### 2. 初始化后端

```bash
cp .env.example .env
uv sync --dev
```

按需追加可选能力：

```bash
uv sync --dev --extra pdf           # 知识库文档入库（文本转 PDF 与解析）
uv sync --dev --extra docling       # Docling 文档解析
uv sync --dev --extra elasticsearch # Elasticsearch 向量库
uv sync --dev --extra web-fetch     # Crawl4AI 网页抓取
uv sync --dev --extra mem0          # Mem0 长期记忆
uv sync --dev --extra oracle        # Oracle DDL fetcher
uv sync --dev --extra opensandbox   # sandbox 执行后端
uv sync --dev --extra feishu        # 飞书长连接
uv sync --dev --extra phoenix       # Phoenix 可观测性
uv sync --dev --extra object-storage # MinIO / S3 对象存储
```

> 知识库上传文档依赖 `pdf` extra。缺少时上传会返回
> `PDF 解析需要 PyMuPDF，请执行 uv sync --extra pdf 安装`。

### 3. 配置 `.env`

必需项（其余可保持默认）：

```dotenv
OPENAI_API_BASE=http://localhost:8082/v1
OPENAI_API_KEY=your-api-key
CHAT_MODEL_NAME=qwen3
EMBEDDING_MODEL_NAME=qwen3-embedding
```

存储与检索按部署形态配置：

```dotenv
# 只跑通用 Agent：可以不配 PostgreSQL，Run/Thread/检查点使用内存，重启即丢失
# 知识库/RAG 需要向量库，二选一：

# 方案 A：PostgreSQL + pgvector
PG_DATABASE_URL=postgresql://admin:admin@localhost:5432/deepclaw
VECTOR_STORE_BACKEND=pgsql

# 方案 B：Elasticsearch
# VECTOR_STORE_BACKEND=elasticsearch
# ES_URL=http://localhost:9200
# ES_URSR=elastic
# ES_PWD=elastic@2024

# 知识库文件对象存储：默认本地，也可切换 MinIO
OBJECT_STORAGE_PROVIDER=local
# LOCAL_STORAGE_ROOT=.deepclaw/workspace/pdf_files
# OBJECT_STORAGE_PROVIDER=minio
# MINIO_ENDPOINT_URL=http://localhost:9000
# MINIO_ACCESS_KEY=minioadmin
# MINIO_SECRET_KEY=minioadmin
```

> 只有配置了 `PG_DATABASE_URL`，Run / Thread / 检查点才会落到共享库，多实例部署才能共享会话状态；
> 未配置时使用内存检查点，重启即丢失。

### 4. 启动主服务

统一从 `main` 入口启动：

```bash
uv run python -m deepclaw.main
```

服务启动后：

- 前端页面：`http://localhost:7869/`
- AG-UI Runs：`POST /api/agui/runs`
- AG-UI Agents：`GET /api/agui/agents`
- Channels API：`/api/channels/*`

首次启动时，如果配置了 `AUTH_ADMIN_EMAIL` / `AUTH_ADMIN_PASSWORD` 且系统中还没有管理员，
会自动创建这个管理员账号。未登录访问会自动降级为游客身份，技能管理与知识库管理对游客开放。

### 5. 启动依赖服务（可选，但推荐）

如果用到 Elasticsearch 知识库或 Postgres 长期记忆，需启动对应服务：

```bash
docker compose -f docker-compose.middleware.yml up -d postgresql elasticsearch
```

如需 Phoenix 观测：

```bash
docker compose -f docker-compose.middleware.yml up -d phoenix
```

如果要用容器方式跑主服务，中间件和应用分开编排：

```bash
docker compose -f docker-compose.middleware.yml up -d   # 先起中间件
docker compose -f docker-compose.app.yml up -d          # 再起应用
```

Phoenix 控制台默认地址：`http://localhost:6006`

### 6. 启动 OpenSandbox 服务（可选，仅 sandbox 模式需要）

如果使用 `BACKEND_TYPE=sandbox`，需要额外启动 OpenSandbox Server 并拉取镜像：

```bash
# 拉取所需镜像
docker pull sandbox-registry.cn-zhangjiakou.cr.aliyuncs.com/opensandbox/code-interpreter:v1.0.2
docker pull opensandbox/execd:v1.0.16
docker pull opensandbox/egress:v1.0.12

# 启动 OpenSandbox Server（需先配置 .sandbox.toml）
opensandbox-server --config .sandbox.toml
```

### 7. 前端开发

仅在你需要开发或重新构建前端时执行：

```bash
cd frontend
pnpm install
pnpm dev
```

开发模式地址：`http://localhost:3000`

构建静态前端并交给后端托管：

```bash
cd frontend
pnpm build
```

## API 接口

业务接口支持游客访问；未携带 `Authorization: Bearer <token>` 时按游客身份处理。
用户管理接口以及渠道全量范围等管理能力需要管理员角色，不能以游客身份调用。

### 认证

| 方法 | 路径 | 用途 |
|------|------|------|
| `POST` | `/api/auth/register` | 注册普通用户并返回访问令牌 |
| `POST` | `/api/auth/login` | 邮箱密码登录 |
| `POST` | `/api/auth/logout` | 撤销当前访问令牌 |
| `GET` | `/api/auth/me` | 返回当前鉴权主体 |
| `POST` | `/api/auth/users/create` | 管理员创建用户（可指定角色） |
| `POST` | `/api/auth/users/list` | 管理员查询用户列表 |
| `POST` | `/api/auth/users/update-role` | 管理员调整用户角色 |
| `POST` | `/api/auth/users/update-status` | 管理员启用 / 停用用户 |
| `POST` | `/api/auth/users/reset-password` | 管理员重置用户密码 |

访问令牌是服务端不透明令牌（`la_` 前缀 + 随机串，数据库只存 SHA-256 哈希），默认 1 天有效。
停用用户或重置密码会即时撤销该用户全部令牌。

### 运行时配置

| 方法 | 路径 | 用途 |
|------|------|------|
| `GET` | `/api/runtime-config` | 返回前端使用的 AG-UI Runs 与 Agents 路径 |

### AG-UI（统一 Agent/RAG）

| 方法 | 路径 | 协议 | 用途 |
|------|------|------|------|
| `GET` | `/api/agui/agents` | REST | 查询可用智能体 |
| `POST` | `/api/agui/runs` | AG-UI | 创建 Run，顶层 `agentId` 选择智能体 |
| `GET` | `/api/agui/runs/{run_id}/events` | AG-UI SSE | 续流或重放 Run 事件 |
| `GET` | `/api/agui/runs/{run_id}` | REST | Run Snapshot |
| `POST` | `/api/agui/runs/{run_id}/resume` | AG-UI | 恢复中断 Run |
| `POST` | `/api/agui/runs/{run_id}/cancel` | REST | 取消 Run |
| `GET` | `/api/agui/threads` | REST | Thread 列表 |
| `GET` | `/api/agui/threads/{thread_id}/runs` | REST | Thread 下的 Run 列表 |
| `GET` | `/api/agui/threads/{thread_id}/state` | REST | Thread 图状态 |
| `DELETE` | `/api/agui/threads/{thread_id}` | REST | 删除 Thread |

### Agent 管理

| 方法 | 路径 | 协议 | 用途 |
|------|------|------|------|
| `POST` | `/api/agent/skills/list` | REST | 技能列表 |
| `POST` | `/api/agent/skills/upload` | REST | 上传技能 zip |
| `POST` | `/api/agent/skills/delete` | REST | 删除技能 |

### 知识库

| 方法 | 路径 | 协议 | 用途 |
|------|------|------|------|
| `POST` | `/api/rag/knowledge-bases/list` | REST | 知识库分页列表 |
| `POST` | `/api/rag/knowledge-bases/create` | REST | 创建知识库 |
| `POST` | `/api/rag/knowledge-bases/detail` | REST | 知识库详情 |
| `POST` | `/api/rag/knowledge-bases/update` | REST | 更新知识库 |
| `POST` | `/api/rag/knowledge-bases/delete` | REST | 删除知识库 |
| `POST` | `/api/rag/knowledge-bases/bulk-delete` | REST | 批量删除知识库 |
| `POST` | `/api/rag/knowledge-bases/documents/list` | REST | 文档分页列表 |
| `POST` | `/api/rag/knowledge-bases/documents/detail` | REST | 文档切片详情 |
| `POST` | `/api/rag/knowledge-bases/documents/upload` | REST | 上传文档 |
| `POST` | `/api/rag/knowledge-bases/documents/update` | REST | 更新文档展示名 |
| `POST` | `/api/rag/knowledge-bases/documents/delete` | REST | 删除文档 |
| `POST` | `/api/rag/knowledge-bases/documents/bulk-delete` | REST | 批量删除文档 |

### Channels

| 方法 | 路径 | 协议 | 用途 |
|------|------|------|------|
| `GET` | `/api/channels/bindings` | REST | 查询渠道绑定列表（`scope=my\|all`） |
| `POST` | `/api/channels/feishu/events` | REST | 飞书事件入口 |
| `POST` | `/api/channels/feishu/bindings` | REST | 创建飞书绑定 |
| `DELETE` | `/api/channels/feishu/bindings/{binding_id}` | REST | 删除飞书绑定 |
| `POST` | `/api/channels/dingtalk/events` | REST | 钉钉事件入口 |
| `POST` | `/api/channels/weixin-clawbot/bindings` | REST | 创建微信 ClawBot 绑定 |
| `POST` | `/api/channels/weixin-clawbot/bindings/{binding_id}/qrcode` | REST | 刷新微信 ClawBot 绑定二维码 |
| `GET` | `/api/channels/weixin-clawbot/bindings/{binding_id}/qrcode/status` | REST | 查询微信 ClawBot 绑定二维码状态 |
| `DELETE` | `/api/channels/weixin-clawbot/bindings/{binding_id}` | REST | 删除微信 ClawBot 绑定 |
| `POST` | `/api/channels/weixin-clawbot/poll` | REST | 拉取微信 ClawBot 待处理消息 |
| `GET` | `/api/channels/sessions` | REST | 列出渠道会话 |
| `PATCH` | `/api/channels/sessions/{session_id}` | REST | 更新会话回复模式 |

## 使用示例

以下示例假设服务运行在 `http://localhost:7869`。除需要管理员权限的接口外，业务请求都可以省略
`Authorization` 头（此时按游客身份处理）。

### 获取访问令牌

```bash
TOKEN=$(curl -s -X POST http://localhost:7869/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@example.com","password":"Admin123456"}' \
  | python -c "import json,sys; print(json.load(sys.stdin)['token'])")
```

### 通用 Agent 问答

`agentId` 省略时使用默认智能体 `agent`。`threadId` 决定会话归属，同一个 `threadId` 会自动续接历史。

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
      { "id": "msg-1", "role": "user", "content": "帮我查一下明天上海的天气" }
    ],
    "tools": [],
    "context": [],
    "forwardedProps": {}
  }'
```

返回 `202` 与 Run 快照（`runId` / `threadId` / `agentId` / `status` / `lastEventId`）。

### 订阅事件流

```bash
curl -N http://localhost:7869/api/agui/runs/run-demo-1/events \
  -H "Authorization: Bearer $TOKEN" \
  -H "Last-Event-ID: run-demo-1:12"
```

事件为标准 AG-UI 事件（`TEXT_MESSAGE_CONTENT`、`TOOL_CALL_START`、`TOOL_CALL_RESULT` 等）。
带上 `Last-Event-ID` 可以从指定序号重放，断线重连不会丢事件。

### 恢复中断（人工确认）

工具调用被配置为需要审批时，服务会以 `RUN_FINISHED.outcome` 返回中断信息。恢复走**同一个 Run**，
把决策放进顶层 `resume[]`：

```bash
curl -X POST http://localhost:7869/api/agui/runs/run-demo-1/resume \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "agentId": "agent",
    "threadId": "demo-thread",
    "runId": "run-demo-1",
    "messages": [
      { "id": "msg-1", "role": "user", "content": "帮我查一下明天南阳的天气" }
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

### 知识库问答

`index_name` / `graph_name` 取自知识库详情的 `passage_index` 与 `index_prefix`：

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
      { "id": "msg-1", "role": "user", "content": "这份文档的核心结论是什么？" }
    ],
    "tools": [],
    "context": [],
    "forwardedProps": {}
  }'
```

### 创建知识库并上传文档

```bash
# 创建知识库（归属用户由服务端从令牌推导，游客固定为 guest）
curl -X POST http://localhost:7869/api/rag/knowledge-bases/create \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"user_id":"demo-user","name":"产品文档","description":"示例知识库"}'

# 上传文档（需要 uv sync --extra pdf）
curl -X POST http://localhost:7869/api/rag/knowledge-bases/documents/upload \
  -H "Authorization: Bearer $TOKEN" \
  -F "user_id=demo-user" \
  -F "knowledge_base_id=<knowledge_base_id>" \
  -F "files=@./产品介绍.md"
```

### 查询 Thread

```bash
curl http://localhost:7869/api/agui/threads -H "Authorization: Bearer $TOKEN"
curl http://localhost:7869/api/agui/threads/demo-thread/runs -H "Authorization: Bearer $TOKEN"
curl http://localhost:7869/api/agui/threads/demo-thread/state -H "Authorization: Bearer $TOKEN"
```

`/state` 返回 LangGraph 图状态，并额外附带 `message_created_at`
（`messageId -> UTC ISO8601`），用于前端展示每条消息的真实时间。

## 配置说明

### 必填环境变量

| 变量 | 说明 |
|------|------|
| `OPENAI_API_BASE` | OpenAI 兼容 LLM 网关地址 |
| `OPENAI_API_KEY` | LLM 网关密钥 |
| `CHAT_MODEL_NAME` | 聊天模型名称 |
| `EMBEDDING_MODEL_NAME` | 向量模型名称，知识库入库与检索使用 |

### 存储与检索

| 变量 | 说明 |
|------|------|
| `PG_DATABASE_URL` | PostgreSQL 连接串。配置后 Run/Thread、检查点、长期记忆、认证、渠道与知识库元数据统一落库，多实例可共享 |
| `VECTOR_STORE_BACKEND` | 向量库后端：`pgsql`（PostgreSQL + pgvector）或 `elasticsearch`，默认 `elasticsearch` |
| `ES_URL` | `VECTOR_STORE_BACKEND=elasticsearch` 时的 Elasticsearch 地址 |
| `ES_URSR` / `ES_PWD` | Elasticsearch 用户名与密码 |
| `OBJECT_STORAGE_PROVIDER` | 知识库文件对象存储：`local`（默认）或 `minio` |
| `LOCAL_STORAGE_ROOT` | 本地对象存储根目录，默认 `.deepclaw/workspace/pdf_files`；实际路径为 `root/bucket_name/file_path` |
| `MINIO_ENDPOINT_URL` / `MINIO_ACCESS_KEY` / `MINIO_SECRET_KEY` | `OBJECT_STORAGE_PROVIDER=minio` 时必填 |

### 常用可选环境变量

| 变量 | 说明 |
|------|------|
| `HOST` / `PORT` | 监听地址与端口，默认 `0.0.0.0:7869` |
| `BACKEND_TYPE` | 执行后端：`local_shell`（默认）/ `store` / `sandbox` |
| `OPEN_SANDBOX_CODE_INTERPRETER_IMAGE` | Sandbox 代码解释器镜像地址（默认：`sandbox-registry.cn-zhangjiakou.cr.aliyuncs.com/opensandbox/code-interpreter:v1.0.2`） |
| `TAVILY_API_KEY` | 启用联网搜索工具 |
| `USE_TOOL_SEARCH` | 启用延迟工具搜索 |
| `USE_COPILOTKIT` | 启用 CopilotKit 中间件 |
| `MCP_CONFIG` | 默认 MCP 服务配置（JSON） |
| `PHOENIX_COLLECTOR_ENDPOINT` | 启用 Phoenix tracing |
| `AUTH_ADMIN_EMAIL` / `AUTH_ADMIN_PASSWORD` | 首次启动时自举的管理员账号 |
| `AUTH_TOKEN_EXPIRE_DAYS` | 访问令牌有效期天数，默认 `1` |
| `AGUI_RUN_RETENTION_SECONDS` | Run 与事件的保留时长，默认 `3600` |
| `AGUI_THREAD_RETENTION_SECONDS` | Thread 索引保留时长；默认 `0` 表示不自动过期 |
| `AGUI_RUN_MAX_EVENTS` | 单个 Run 的事件数量上限，默认 `2000` |
| `AGUI_RUN_CLEANUP_INTERVAL_SECONDS` | 过期清理任务间隔，默认 `60` |
| `AGUI_RUN_POLL_INTERVAL_SECONDS` | 事件流轮询间隔，默认 `0.5` |
| `CHART_PUBLIC_URL` | 图表对外访问前缀，留空则返回相对路径 `/charts/xxx.png` |
| `CHART_RETENTION_HOURS` / `CHART_MAX_FILES` | 图表文件保留时长与数量上限 |
| `CHANNEL_AGENT_API_URL` | 渠道网关调用 Agent 的完整地址；留空时自动使用当前服务的 `/api/agui/runs` |
| `WEIXIN_CLAWBOT_*` | 微信 ClawBot 相关配置 |

## 沙箱模式（多用户工作隔离）

当 `BACKEND_TYPE=sandbox` 时，系统使用 [OpenSandbox](https://github.com/opensandbox/opensandbox) 为每个用户创建独立的 Docker 容器作为执行环境，实现多用户工作隔离。

### 隔离机制

| 隔离维度 | 说明 |
|----------|------|
| 容器隔离 | 每个用户拥有独立的 OpenSandbox 容器，进程和文件系统完全隔离 |
| 工作区隔离 | 每个用户的工作区映射到 `user_workspace/{user_id}/.deepclaw/`，通过 Docker bind mount 挂载 |
| 技能目录隔离 | 私有技能目录（`/.deepclaw/workspace/skills`）随用户独立挂载，同时共享公共技能目录（`/workspace/skills`） |
| 会话历史隔离 | 对话历史写入各自独立的 `conversation_history` 目录 |
| 生命周期管理 | 每次 Agent 执行完毕后，`OpenSandboxKillMiddleware` 自动杀死当前用户沙箱并清理状态 |

### 执行流程

1. Agent 启动时检查 `BACKEND_TYPE`，若为 `sandbox` 则加载 `OpenSandbox` 后端
2. 首次执行时，`get_sandbox()` 为当前 `user_id` 创建新沙箱，在 runtime store 中持久化 `sandbox_id`
3. 后续执行复用已有沙箱（通过 `sandbox_id` 重连）
4. 沙箱内支持：命令执行（`execute`）、文件读写（`write`/`read`）、文件编辑（`edit`）、文件上传下载（`upload_files`/`download_files`）
5. Agent 执行完毕后，`OpenSandboxKillMiddleware.after_agent` 自动杀死沙箱并删除 store 中的记录

### 前提条件

- Docker 环境
- OpenSandbox Server 已启动（参考上文步骤 6）
- 正确配置 `.sandbox.toml`（项目根目录已有示例配置）
- 安装 `opensandbox` 额外依赖：`uv sync --dev --extra opensandbox`

### 配置文件 `.sandbox.toml`

项目根目录的 `.sandbox.toml` 是 OpenSandbox Server 的配置文件，关键项：

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

`allowed_host_paths` 必须填写项目根目录的绝对路径，否则 bind mount 会被拒绝。

## 常见说明

- 后端会直接挂载 `frontend/out`。如果该目录已经存在，纯运行场景不需要安装 Node.js 和 pnpm。
- 前端修改后，必须重新执行 `pnpm build`，后端 `/` 才会提供最新页面。
- 默认工作区位于 `.deepclaw/workspace`，技能包、图表与上传的原始文件都在这里。
- 未配置 `PG_DATABASE_URL` 时，认证、渠道、知识库元数据各自回退到 `.deepclaw/` 下的 SQLite，
  检查点使用内存实现，**重启后会话丢失，也无法多实例共享**。
- 未携带令牌访问会按游客身份处理，游客同样可以管理技能与知识库；只有用户管理需要管理员角色。
- 所有数据库操作都基于 SQLModel 异步会话，不要在 Web 层引入同步数据库调用。
- 如果 `frontend/out` 不存在，后端仍可提供 API，但 `/` 不会挂载前端页面。
- 沙箱模式（`BACKEND_TYPE=sandbox`）需要先启动 OpenSandbox Server 并正确配置 `.sandbox.toml`，详见上方的「沙箱模式」章节。
- 新增智能体不需要改动 Web 路由：在 `deepclaw/agents/<name>/agent.py` 定义 `Agent` 子类即可被自动发现，
  前端通过 `GET /api/agui/agents` 拿到列表，用顶层 `agentId` 调用。
- `CronMiddleware` 已提供 cron 工具，但默认 Agent 未启用；需要时在 Agent 的 middleware 列表中显式加入。
- `.env` 含密钥，不要提交到 Git；仓库只维护 `.env.example`。

## License

Apache-2.0
