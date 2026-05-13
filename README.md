<h1 align="center">LangChain Agent API</h1>

<p align="center">
  <img alt="LangGraph" src="https://img.shields.io/badge/LangGraph-Agent-1C3C3C?style=for-the-badge">
  <img alt="Next.js" src="https://img.shields.io/badge/Next.js-15-000000?style=for-the-badge&logo=nextdotjs&logoColor=white">
  <img alt="Elasticsearch" src="https://img.shields.io/badge/Elasticsearch-8.x-005571?style=for-the-badge&logo=elasticsearch&logoColor=white">
  <img alt="License" src="https://img.shields.io/badge/License-Apache--2.0-blue?style=for-the-badge">
</p>

<p align="center">
  <a href="#快速开始">快速开始</a>
  ·
  <a href="#核心能力">核心能力</a>
  ·
  <a href="#api-接口">API 接口</a>
  ·
  <a href="#配置说明">配置说明</a>
  ·
  <a href="#开发指南">开发指南</a>
</p>

LangChain Agent API 是一个面向二次开发的智能 Agent 服务骨架。项目把 Agent、RAG、工具调用、流式协议、技能管理和前端聊天界面整合到同一个 FastAPI 服务中，适合快速搭建企业知识库问答、自动化助手、内部 Copilot 和多工具智能体应用。

## 核心能力

| 能力 | 说明 |
|------|------|
| Agent 编排 | 基于 LangGraph / DeepAgents 构建，支持 DeepAgent 与 ReactAgent 扩展 |
| RAG 知识库 | Elasticsearch 混合检索、向量图 RAG、实体关系扩展和文档管理 |
| 工具调用 | 内置天气、网页抓取、定时任务等工具，并支持 MCP 扩展 |
| 流式输出 | 提供 SSE 通用接口和 AG-UI 协议接口，适配实时聊天体验 |
| 多执行后端 | 支持 `local_shell`、`store`、`sandbox` 三种执行模式 |
| 前端界面 | Next.js + React 聊天 UI，构建后由 FastAPI 统一托管 |
| 可观测性 | 可选接入 Phoenix tracing 和 LangSmith |

## 界面预览

![聊天界面](assets/img/chat.png)

## 技术栈

| 模块 | 技术 |
|------|------|
| 后端 | FastAPI, LangGraph, DeepAgents, LangChain |
| RAG | Elasticsearch, Dense Vector, BM25, Graph RAG |
| 模型接入 | OpenAI-compatible API, DeepSeek adapter |
| 前端 | Next.js 15, React 19, TypeScript |
| 存储 | Elasticsearch, PostgreSQL 可选, 本地工作区 |
| 可观测性 | Phoenix, LangSmith |
| 包管理 | uv, pnpm |

## 项目结构

```text
langchain-api/
├── langchain_api/
│   ├── agent/              # Agent 构建、上下文、状态和管理接口
│   ├── api/                # FastAPI 路由注册和协议适配
│   ├── middleware/         # 业务开关、RAG 注入、工具搜索、沙箱中间件
│   ├── rag/                # Elasticsearch 检索、向量图 RAG、知识库管理
│   ├── tools/              # 天气、网页抓取、定时任务等工具
│   ├── main.py             # 唯一 FastAPI 启动入口
│   └── settings.py         # 环境变量配置
├── frontend/               # Next.js + React 前端
│   ├── app/
│   └── components/
├── assets/                 # 截图、插件等静态资源
├── .langchain_api/         # 运行工作区
└── docker-compose.yml      # PostgreSQL / Elasticsearch / Phoenix
```

## 快速开始

### 1. 环境要求

| 依赖 | 版本 |
|------|------|
| Python | `>= 3.12` |
| Node.js | `>= 18` |
| uv | 最新稳定版 |
| pnpm | 最新稳定版 |
| Elasticsearch | `8.x` |

### 2. 启动依赖服务

```bash
docker-compose up -d postgresql elasticsearch
```

如需链路观测：

```bash
docker-compose up -d phoenix
```

Phoenix 控制台默认地址：`http://localhost:6006`

### 3. 初始化后端

```bash
cp .env.example .env
uv sync --dev
```

编辑 `.env`，至少填入：

```dotenv
OPENAI_API_BASE=http://localhost:8082/v1
OPENAI_API_KEY=your-api-key
CHAT_MODEL_NAME=qwen3
EMBEDDING_MODEL_NAME=qwen3-embedding
ES_URL=http://localhost:9200
ES_URSR=elastic
ES_PWD=elastic@2024
```

### 4. 启动主服务

```bash
uv run uvicorn langchain_api.main:app --reload --host 0.0.0.0 --port 7869
```

服务启动后：

- Agent SSE：`http://localhost:7869/api/agent/general_api`
- RAG SSE：`http://localhost:7869/api/rag/general_api`
- AG-UI：`http://localhost:7869/api/agent/ag_ui`
- 前端静态页：构建后访问 `http://localhost:7869/`

### 5. 前端开发

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

### Agent

| 方法 | 路径 | 协议 | 用途 |
|------|------|------|------|
| `POST` | `/api/agent/ag_ui` | AG-UI | 前端 Agent 交互 |
| `POST` | `/api/agent/general_api` | SSE | 通用 Agent 流式接口 |
| `POST` | `/api/agent/skills/list` | REST | 技能列表 |
| `POST` | `/api/agent/skills/upload` | REST | 上传技能 zip |
| `POST` | `/api/agent/skills/delete` | REST | 删除技能 |

### RAG

| 方法 | 路径 | 协议 | 用途 |
|------|------|------|------|
| `POST` | `/api/rag/general_api` | SSE | RAG 流式问答 |
| `POST` | `/api/rag/knowledge-bases/list` | REST | 知识库列表 |
| `POST` | `/api/rag/knowledge-bases/create` | REST | 创建知识库 |
| `POST` | `/api/rag/knowledge-bases/detail` | REST | 知识库详情 |
| `POST` | `/api/rag/knowledge-bases/update` | REST | 更新知识库 |
| `POST` | `/api/rag/knowledge-bases/delete` | REST | 删除知识库 |
| `POST` | `/api/rag/knowledge-bases/bulk-delete` | REST | 批量删除知识库 |
| `POST` | `/api/rag/knowledge-bases/documents/list` | REST | 文档列表 |
| `POST` | `/api/rag/knowledge-bases/documents/detail` | REST | 文档详情 |
| `POST` | `/api/rag/knowledge-bases/documents/upload` | REST | 上传文档 |
| `POST` | `/api/rag/knowledge-bases/documents/update` | REST | 更新文档展示名 |
| `POST` | `/api/rag/knowledge-bases/documents/delete` | REST | 删除文档 |
| `POST` | `/api/rag/knowledge-bases/documents/bulk-delete` | REST | 批量删除文档 |

## 使用示例

### 创建知识库

```bash
curl -X POST http://localhost:7869/api/rag/knowledge-bases/create \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "demo-user",
    "name": "产品文档",
    "description": "用于演示的知识库"
  }'
```

### 上传文档

`knowledge_base_id` 使用创建知识库接口返回的值。

```bash
curl -X POST http://localhost:7869/api/rag/knowledge-bases/documents/upload \
  -F "user_id=demo-user" \
  -F "knowledge_base_id=<knowledge_base_id>" \
  -F "files=@document.pdf"
```

### 调用 RAG 流式问答

`index_name` 和 `graph_name` 可从知识库详情中的 `passage_index`、`index_prefix` 字段获取。

```bash
curl -N -X POST http://localhost:7869/api/rag/general_api \
  -H "Content-Type: application/json" \
  -d '{
    "query": "这份文档的核心结论是什么？",
    "session_id": "demo-thread",
    "user_id": "demo-user",
    "index_name": "kb_<knowledge_base_id>_passages",
    "graph_name": "kb_<knowledge_base_id>"
  }'
```

## 配置说明

### 必填环境变量

| 变量 | 说明 |
|------|------|
| `OPENAI_API_BASE` | OpenAI-compatible LLM API 地址 |
| `OPENAI_API_KEY` | LLM API 密钥 |
| `CHAT_MODEL_NAME` | 聊天模型名称，例如 `qwen3` |
| `EMBEDDING_MODEL_NAME` | 向量模型名称，例如 `qwen3-embedding` |
| `ES_URL` | Elasticsearch 地址 |
| `ES_URSR` | Elasticsearch 用户名 |
| `ES_PWD` | Elasticsearch 密码 |

### 可选环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `BACKEND_TYPE` | `local_shell` | 执行后端：`local_shell` / `store` / `sandbox` |
| `TAVILY_API_KEY` | 空 | 启用联网搜索工具 |
| `PG_DATABASE_URL` | 空 | 启用 PostgresStore 持久化记忆 |
| `USE_TOOL_SEARCH` | `False` | 启用延迟工具加载 |
| `USE_COPILOTKIT` | `False` | 启用 CopilotKit 中间件 |
| `PHOENIX_COLLECTOR_ENDPOINT` | 空 | 启用 Phoenix tracing |
| `LANGSMITH_API_KEY` | 空 | 启用 LangSmith 相关能力 |

## RAG 工作流

```text
文档上传
  -> 文本解析与切分
  -> 向量索引 + BM25 索引
  -> 实体 / 关系抽取
  -> 图索引构建
  -> 查询改写
  -> 向量召回 + 图扩展
  -> 上下文组装
  -> LLM 生成
```

RAG 模块位于 `langchain_api/rag/`，核心能力包括：

- `ElasticGraphRAG.add_texts()`：文本入库并构建图索引
- `ElasticGraphRAG.add_documents()`：Document 入库并构建图索引
- `ElasticGraphRAG.retrieve()`：实体召回、关系扩展、passage 回收
- `ElasticGraphRAG.delete_documents()`：删除文档并清理孤立图节点
- `ElasticGraphRAG.delete_graph()`：删除当前图的实体、关系和 passage 索引

## Agent 与工具

Agent 默认使用 DeepAgent，并通过中间件组合业务能力：

- `BusinessMiddleware`：处理 `internet_search`、`deep_thinking` 等业务开关
- `DeferredToolMiddleware`：在 `USE_TOOL_SEARCH=True` 时延迟加载工具
- `RAGMiddleware`：在 RAG Agent 中负责查询改写、检索和上下文注入

内置工具：

| 工具 | 说明 |
|------|------|
| `weather` | 天气查询 |
| `web_fetch` | 网页内容抓取 |
| `cron_manager` | 定时任务管理 |

## Sandbox 后端

启用沙箱执行：

```dotenv
BACKEND_TYPE=sandbox
```

启动 OpenSandbox：

```bash
opensandbox-server --config .sandbox.toml
```

Sandbox 依赖 Playwright：

```bash
playwright install --with-deps chromium
```

## 开发指南

### 后端检查

修改 Python 文件后，优先执行：

```bash
uv run python -m py_compile <changed_file.py>
```

### 前端检查

修改前端后，优先执行：

```bash
cd frontend
pnpm lint
pnpm build
```

### 工作区

`.langchain_api/workspace` 是运行期工作区，常见内容：

| 路径 | 用途 |
|------|------|
| `skills/` | 自定义技能定义 |
| `pdf_files/` | 上传的知识库文档 |
| `converted_pdf/` | 转换后的文本内容 |

## 许可证

本项目基于 [Apache License 2.0](LICENSE) 发布。
