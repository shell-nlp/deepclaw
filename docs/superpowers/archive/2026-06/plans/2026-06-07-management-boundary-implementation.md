# Management Boundary Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将技能管理和知识库管理实现从 `agent/`、`rag/` 核心目录迁移到独立的 `management/` 包，理顺目录职责，同时保持现有接口和行为不变。

**Architecture:** 新增 `deepclaw/management/` 包承载纯管理型服务实现，API 路由层继续保留在 `deepclaw/api/...`，核心运行时目录 `deepclaw/agent/` 与 `deepclaw/rag/` 只保留智能体与检索相关逻辑。迁移过程中仅调整模块位置和导入路径，不修改对外路由和内部业务行为。

**Tech Stack:** Python 3.12、FastAPI、Pydantic、Elasticsearch、CodeGraph、Ruff

---

### Task 1: 建立新的 management 包结构

**Files:**
- Create: `deepclaw/management/__init__.py`
- Create: `deepclaw/management/skill_manager.py`
- Create: `deepclaw/management/knowledge_base_manager.py`

- [ ] **Step 1: 新建包导出文件**

```python
"""管理类服务实现包。"""

__all__ = [
    "knowledge_base_manager",
    "skill_manager",
]
```

- [ ] **Step 2: 迁移技能管理实现**

```python
from deepclaw.constant import workspace_path
from deepclaw.settings import settings


class SkillManager:
    SKILLS_ROOT = workspace_path / "skills"
```

- [ ] **Step 3: 迁移知识库管理实现**

```python
from deepclaw.rag.elastic_graph_rag import ElasticGraphRAG
from deepclaw.rag.elastic_utils import Elasticsearch
from deepclaw.rag.text_splitter import PDFParser
```

- [ ] **Step 4: 保持模块实例名不变**

```python
skill_manager = SkillManager()
knowledge_base_manager = KnowledgeBaseManager(...)
```

### Task 2: 更新 API 路由引用

**Files:**
- Modify: `deepclaw/api/agent/api/skills.py`
- Modify: `deepclaw/api/rag/api/knowledge_bases.py`

- [ ] **Step 1: 调整技能管理导入路径**

```python
from deepclaw.management.skill_manager import (
    SkillDeleteResponse,
    SkillListResponse,
    SkillUploadResponse,
    skill_manager,
)
```

- [ ] **Step 2: 调整知识库管理导入路径**

```python
from deepclaw.management.knowledge_base_manager import (
    BulkDeleteDocumentResponse,
    BulkDeleteKnowledgeBaseResponse,
    KnowledgeBaseDeleteResult,
    knowledge_base_manager,
)
```

- [ ] **Step 3: 保持现有路由、响应模型和异常处理不变**

```python
def _handle_value_error(exc: ValueError) -> HTTPException:
    return HTTPException(status_code=400, detail=str(exc))
```

### Task 3: 清理旧入口并同步文档

**Files:**
- Delete: `deepclaw/agent/skill_manager.py`
- Delete: `deepclaw/rag/knowledge_base.py`
- Modify: `AGENTS.md`

- [ ] **Step 1: 删除旧目录中的实现文件**

```text
删除后不保留兼容壳模块，避免继续误导后续开发把管理逻辑放回核心目录。
```

- [ ] **Step 2: 更新 AGENTS.md 中的结构说明**

```markdown
- `deepclaw/management/skill_manager.py`
  技能文件管理逻辑，供技能管理接口调用。

- `deepclaw/management/knowledge_base_manager.py`
  知识库管理核心实现，负责知识库元数据、文档元数据、文档上传、切片查询和删除。
```

### Task 4: 验证迁移结果

**Files:**
- Test: `deepclaw/management/*.py`
- Test: `deepclaw/api/agent/api/skills.py`
- Test: `deepclaw/api/rag/api/knowledge_bases.py`

- [ ] **Step 1: 运行 Python 语法检查**

Run: `uv run python -m py_compile deepclaw/management/__init__.py deepclaw/management/skill_manager.py deepclaw/management/knowledge_base_manager.py deepclaw/api/agent/api/skills.py deepclaw/api/rag/api/knowledge_bases.py`
Expected: 命令退出码为 0，无语法错误输出

- [ ] **Step 2: 运行 Ruff**

Run: `uv run ruff check .`
Expected: 命令退出码为 0，仓库通过静态检查

- [ ] **Step 3: 更新 CodeGraph 索引**

Run: `codegraph index --force`
Expected: 索引成功完成，后续结构查询基于最新代码

