# Web Backend 目录重构设计

## 目标

将当前分散在 `langchain_api/api`、`langchain_api/auth`、`langchain_api/channels`、`langchain_api/management` 的 Web 相关代码统一收口到 `langchain_api/web_backend`，采用“扁平的按功能聚合”结构，明确区分：

- `web_backend`：FastAPI 应用壳、HTTP 路由、认证、渠道、技能管理、知识库管理等面向 Web 的应用层代码
- `agent`、`rag`、`common`、`middleware`、`tools`：智能体、RAG、算法和通用能力

本次重构不保留旧导入路径兼容层，所有仓库内导入、测试、文档和启动说明全部同步切换到新路径。

## 目标结构

```text
langchain_api/
  web_backend/
    app.py
    lifespan.py
    common/
      endpoints.py
    agent/
      router.py
    rag/
      router.py
    auth/
      router.py
      schemas.py
      service.py
      store.py
      models.py
      security.py
      dependencies.py
    channels/
      router.py
      schemas.py
      service.py
      store.py
      models.py
      config.py
      dispatcher.py
      lifespan.py
      weixin_startup.py
      adapters/
    skills/
      router.py
      schemas.py
      service.py
    knowledge_bases/
      router.py
      schemas.py
      service.py
```

## 重构原则

- 只把面向 Web 的业务代码移动到 `web_backend`，不把算法、Agent 组装、RAG 中间件、ES 工具等一起混入。
- 同一功能下的 `router`、`schemas`、`service`、`store`、`models` 尽量放在一个目录内，减少跨目录跳转。
- 目录命名使用业务名词，不再保留 `management` 这种职责宽泛的名称。
- `agent` 和 `rag` 在 `web_backend` 中只保留 HTTP 入口，不复制其核心实现。
- 保持对外 HTTP 路径不变，避免前端和渠道侧调用行为回归。

## 旧目录到新目录的映射

### 应用入口

- `langchain_api/main.py` → `langchain_api/web_backend/app.py`
- 生命周期相关初始化逻辑从 `main.py` 抽到 `langchain_api/web_backend/lifespan.py`

### Agent HTTP 入口

- `langchain_api/api/agent/api/routes.py` → `langchain_api/web_backend/agent/router.py`
- `langchain_api/api/agent/api/skills.py` 中的技能管理路由拆出：
  - Agent SSE / AG-UI 路由保留在 `web_backend/agent/router.py`
  - 技能管理路由迁移到 `web_backend/skills/router.py`
- `langchain_api/api/common/api/endpoints.py` → `langchain_api/web_backend/common/endpoints.py`

### Auth

- `langchain_api/api/auth/api/routes.py` → `langchain_api/web_backend/auth/router.py`
- `langchain_api/api/auth/schemas/*.py` 合并为 `langchain_api/web_backend/auth/schemas.py`
- `langchain_api/auth/models.py` → `langchain_api/web_backend/auth/models.py`
- `langchain_api/auth/store.py` → `langchain_api/web_backend/auth/store.py`
- `langchain_api/auth/service.py` → `langchain_api/web_backend/auth/service.py`
- `langchain_api/auth/security.py` → `langchain_api/web_backend/auth/security.py`
- `langchain_api/auth/dependencies.py` → `langchain_api/web_backend/auth/dependencies.py`

### Channels

- `langchain_api/api/channels/api/routes.py` → `langchain_api/web_backend/channels/router.py`
- `langchain_api/api/channels/schemas/weixin_clawbot.py` → `langchain_api/web_backend/channels/schemas.py`
- `langchain_api/channels/models.py` → `langchain_api/web_backend/channels/models.py`
- `langchain_api/channels/store.py` → `langchain_api/web_backend/channels/store.py`
- `langchain_api/channels/service.py` → `langchain_api/web_backend/channels/service.py`
- `langchain_api/channels/config.py` → `langchain_api/web_backend/channels/config.py`
- `langchain_api/channels/dispatcher.py` → `langchain_api/web_backend/channels/dispatcher.py`
- `langchain_api/channels/lifespan.py` → `langchain_api/web_backend/channels/lifespan.py`
- `langchain_api/channels/weixin_startup.py` → `langchain_api/web_backend/channels/weixin_startup.py`
- `langchain_api/channels/adapters/*` → `langchain_api/web_backend/channels/adapters/*`
- `langchain_api/channels/agent_client.py` → `langchain_api/web_backend/channels/agent_client.py`

### Skills

- `langchain_api/management/skill_manager.py` → `langchain_api/web_backend/skills/service.py`
- `langchain_api/api/agent/schemas/skills.py` → `langchain_api/web_backend/skills/schemas.py`
- 由 `langchain_api/api/agent/api/skills.py` 提供的路由 → `langchain_api/web_backend/skills/router.py`

### Knowledge Bases

- `langchain_api/management/knowledge_base_manager.py` → `langchain_api/web_backend/knowledge_bases/service.py`
- `langchain_api/api/rag/schemas/knowledge_bases.py` → `langchain_api/web_backend/knowledge_bases/schemas.py`
- `langchain_api/api/rag/api/knowledge_bases.py` → `langchain_api/web_backend/knowledge_bases/router.py`
- `langchain_api/api/rag/api/routes.py` → `langchain_api/web_backend/rag/router.py`

## 启动与装配方式

新的 `web_backend/app.py` 负责：

- 创建 `FastAPI` 应用
- 注册 CORS
- 初始化 agent 的 `checkpointer` 和 `store`
- 统一挂载：
  - `web_backend/auth/router.py`
  - `web_backend/agent/router.py`
  - `web_backend/rag/router.py`
  - `web_backend/channels/router.py`
  - `web_backend/skills/router.py`
  - `web_backend/knowledge_bases/router.py`
- 静态托管 `frontend/out`

新的 `web_backend/lifespan.py` 负责：

- 可观测性初始化
- `patch_langchain()`
- `get_auth_service().bootstrap_admin_if_needed()`
- `channel_lifespan()` 生命周期接入

这样 `app.py` 只保留装配，生命周期副作用与业务模块解耦。

## 导入边界

允许的依赖方向如下：

- `web_backend/*/router.py` 可以依赖同目录下的 `schemas/service/dependencies`
- `web_backend/*/service.py` 可以依赖同目录下的 `store/models/config`
- `web_backend/agent/router.py` 和 `web_backend/rag/router.py` 可以依赖根包下的 `agent`、`rag`
- `web_backend/knowledge_bases/service.py` 可以依赖根包下的 `common`、`rag`、`tools`
- 根包下的核心能力层不反向依赖 `web_backend`

禁止继续保留以下旧模式：

- `api` 路由层再去跨目录调用根包 `management`
- Web 认证逻辑留在根包、路由模型留在 `api` 子树，造成一个功能横跨三四个目录
- 为兼容旧路径而保留空壳转发模块

## HTTP 行为要求

本次重构后，以下公开路径保持不变：

- `/api/auth/*`
- `/api/agent/ag_ui`
- `/api/agent/general_api`
- `/api/agent/skills/*`
- `/api/rag/general_api`
- `/api/rag/knowledge-bases/*`
- `/api/channels/*`

也就是说，本次主要改变 Python 目录结构和内部导入，不主动改变前端、渠道回调、外部调用方的接口契约。

## 本次允许的代码级优化

这次不仅是目录迁移，也允许做与结构直接相关的最小重构：

- 消除明显重复的路由错误处理辅助函数
- 把与功能强绑定的小型 schema 合并，减少无意义拆分
- 修正导入方向不清导致的循环依赖风险
- 把 `main.py` 中的应用装配逻辑收口为更清晰的模块边界

## 不在本次范围内

以下内容不作为本次重构目标：

- 重写 Agent、RAG、Elasticsearch 检索等核心实现
- 改造前端页面结构或 API 调用协议
- 新增认证机制、渠道协议或知识库能力
- 将整个项目进一步拆成多包或 monorepo

## 验证要求

至少执行以下验证：

```bash
uv run python -m py_compile <全部修改过的 Python 文件>
uv run ruff check .
uv run pytest tests -q
codegraph index --force
```

如果本次修改到前端调用路径或静态托管行为，再补充：

```bash
cd frontend
pnpm lint
pnpm build
```

## 风险与应对

### 导入路径大量变化

风险：测试、应用入口、生命周期导入和模块级单例容易一起失效。

应对：优先迁移文件，再统一修正导入，最后集中跑 `py_compile + pytest`。

### 模块级单例位置变化

风险：`get_auth_service()`、`get_channel_store()`、知识库管理器等单例在迁移后可能被重复初始化。

应对：保留原有单例模式，但把实例定义位置固定在各自新模块内，不在多个 router 中重复创建。

### Channels 生命周期耦合较强

风险：`router.py`、`lifespan.py`、`weixin_startup.py`、runtime state 之间导入链较长，迁移时容易出错。

应对：先整体迁移 `channels` 目录，再单独修正 API 路由引用，避免拆一半停一半。

## 产出结果

完成后，仓库应满足：

- `web_backend` 成为唯一的 Web 应用代码聚合目录
- `management` 目录被移除
- `auth`、`channels` 不再挂在根包
- `agent`、`rag` 在 `web_backend` 中只保留 HTTP 入口，在根包中保留核心实现
- `AGENTS.md`、启动命令、测试导入、CodeGraph 索引全部与新结构一致
