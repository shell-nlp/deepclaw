# API 业务目录重组实施计划

> **执行要求：** 用户明确要求不要执行 `git commit`。本计划只描述文件修改和验证步骤。

## 目标

把 `langchain_api/api` 改成业务域内部包含 `api/` 和 `schemas/` 的结构，删除旧兼容导出模块，并把所有调用方迁移到新路径。

## 任务

1. 新增失败测试：
   - 新路径 `langchain_api.api.channels.api.routes` 可导入。
   - 新 schema 路径 `langchain_api.api.channels.schemas.weixin_clawbot` 可导入。
   - 旧路径 `langchain_api.api.routers.channels` 不再可导入。

2. 创建业务内部目录：
   - `agent/api`、`agent/schemas`
   - `rag/api`、`rag/schemas`
   - `channels/api`、`channels/schemas`
   - `common/api`、`common/schemas`

3. 迁移路由实现：
   - `agent/api/routes.py`
   - `agent/api/skills.py`
   - `rag/api/routes.py`
   - `rag/api/knowledge_bases.py`
   - `channels/api/routes.py`
   - `common/api/endpoints.py`

4. 迁移 Pydantic schema：
   - `agent/schemas/skills.py`
   - `rag/schemas/knowledge_bases.py`
   - `channels/schemas/weixin_clawbot.py`
   - `common/schemas/endpoints.py`

5. 删除旧兼容模块：
   - `langchain_api/api/endpoints.py`
   - `langchain_api/api/routers/*`
   - `langchain_api/api/management/*`
   - 第一轮生成的非嵌套实现文件，例如 `agent/routes.py`、`common/endpoints.py`

6. 更新导入：
   - `langchain_api/main.py`
   - 各业务包 `__init__.py`
   - 测试中的 router 导入和 patch 路径

7. 验证：
   - `uv run python -m py_compile <changed-python-files>`
   - `uv run pytest tests/test_channels_router.py`
