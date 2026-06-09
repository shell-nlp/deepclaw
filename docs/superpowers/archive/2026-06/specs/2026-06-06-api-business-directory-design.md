# API 业务目录重组设计

## 目标

重组 `deepclaw/api`，让 API 代码按业务域组织，并在每个业务域内部继续按职责拆分。路由注册代码放在 `api/`，Pydantic 请求/响应模型放在 `schemas/`。本次不保留旧 `routers`、`management`、根部 `endpoints.py` 的兼容导出代码，所有内部导入和测试都迁移到新路径。

## 目标结构

```text
deepclaw/api/
  agent/
    api/
      routes.py
      skills.py
    schemas/
      skills.py
  rag/
    api/
      routes.py
      knowledge_bases.py
    schemas/
      knowledge_bases.py
  channels/
    api/
      routes.py
    schemas/
      weixin_clawbot.py
  common/
    api/
      endpoints.py
    schemas/
      endpoints.py
```

## 迁移规则

- `routes.py` 只负责创建和注册 FastAPI router。
- 业务管理接口仍按业务域放置，例如 `agent/api/skills.py`、`rag/api/knowledge_bases.py`。
- 本地定义的 Pydantic `BaseModel` 全部迁移到对应 `schemas/` 文件。
- `deepclaw/main.py` 继续从业务包导入 `create_agent_router`、`create_rag_router`、`create_channels_router`。
- 删除旧兼容模块，不再使用 `sys.modules[__name__] = ...`。

## 不在本次范围内

本次不新增空的 `models/`、`service.py`、`repository.py`。现有核心业务实现仍保留在：

- `deepclaw/agent`
- `deepclaw/rag`
- `deepclaw/channels`

后续如果某个业务域需要新建 ORM、service 或 repository，再按真实需求补齐。

## HTTP 行为

公开 HTTP 路径保持不变：

- `/api/agent/ag_ui`
- `/api/agent/general_api`
- `/api/agent/skills/*`
- `/api/rag/general_api`
- `/api/rag/knowledge-bases/*`
- `/api/channels/*`

## 验证方式

最小验证：

```bash
uv run python -m py_compile <changed-python-files>
uv run pytest tests/test_channels_router.py
```

