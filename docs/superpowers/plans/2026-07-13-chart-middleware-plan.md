# ChartMiddleware Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 ChartMiddleware 提供 9 种图表生成工具给 LangChain Agent

**Architecture:** 核心渲染层（engine + chart definitions）与中间件适配层（middleware）解耦，核心层零 langchain 依赖，后续可单独发布为 MCP Server。

**Tech Stack:** matplotlib, Pydantic, LangChain AgentMiddleware, FastAPI

## Global Constraints

- 所有新函数/方法必须带中文 docstring（功能说明 + Args 每行）。禁止 `"""...""" ...` 同行。
- 测试统一使用 `pytest`，不要引入 `unittest` 风格。
- 核心渲染层不可依赖 langchain / langgraph。
- 图表保存到 `.deepclaw/workspace/charts/{uuid}.png`。
- 每个图表类型 = 一个 `charts/*.py` 文件，导出 `chart()` -> `ChartDef` 命名元组。
- 中文字体自动探测 fallback。

---

### Task 1: 基础层 — utils + schemas + engine + 依赖

**Files:**
- Create: `deepclaw/middleware/chart/utils.py`
- Create: `deepclaw/middleware/chart/schemas.py`
- Create: `deepclaw/middleware/chart/charts/__init__.py`
- Create: `deepclaw/middleware/chart/engine.py`
- Create: `tests/test_chart_engine.py`
- Modify: `pyproject.toml` (add matplotlib 依赖)

**Interfaces:**
- Produces:
  - `utils.setup_chinese_font() -> str` — 返回可用中文字体名
  - `utils.save_chart_to_workspace(fig: plt.Figure) -> str` — 保存并返回文件 URL
  - `schemas.ThemeSchema`, `schemas.StyleSchema`, `schemas.DimensionsSchema` — 公共 Pydantic 字段
  - `charts.__init__.ALL_CHARTS: list[ChartDef]` — 注册表
  - `charts.__init__.CHART_MAP: dict[str, ChartDef]` — 名称索引
  - `engine.render_chart(chart_type: str, params: dict) -> str` — 统一入口

- [ ] **Step 1: 添加 matplotlib 依赖**

```bash
uv add matplotlib
```

验证：
```bash
uv run python -c "import matplotlib; print(matplotlib.__version__)"
```

- [ ] **Step 2: 创建目录结构**

```bash
New-Item -ItemType Directory -Path "deepclaw/middleware/chart/charts" -Force
New-Item -ItemType Directory -Path "tests/chart" -Force
```

- [ ] **Step 3: 实现 utils.py**

```python
import uuid
from pathlib import Path

import matplotlib.pyplot as plt
from loguru import logger

from deepclaw.constant import workspace_path


_CHARTS_DIR: Path | None = None


def _get_charts_dir() -> Path:
    global _CHARTS_DIR
    if _CHARTS_DIR is None:
        _CHARTS_DIR = workspace_path / "charts"
        _CHARTS_DIR.mkdir(parents=True, exist_ok=True)
    return _CHARTS_DIR


def setup_chinese_font() -> str:
    font_candidates = ["SimHei", "Microsoft YaHei", "PingFang SC", "Noto Sans CJK SC", "WenQuanYi Micro Hei", "DejaVu Sans"]
    available = {f.name for f in plt.font_manager.fontManager.ttflist}
    for name in font_candidates:
        if name in available:
            logger.info("使用中文字体: {}", name)
            return name
    logger.warning("未找到中文字体，回退到 DejaVu Sans")
    return "DejaVu Sans"


def save_chart_to_workspace(fig: plt.Figure) -> str:
    file_name = f"{uuid.uuid4().hex}.png"
    file_path = _get_charts_dir() / file_name
    fig.savefig(file_path, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    logger.info("图表已保存: {}", file_path)
    return f"/charts/{file_name}"
```

- [ ] **Step 4: 实现 schemas.py**

```python
from pydantic import BaseModel, Field


class StyleSchema(BaseModel):
    """图表样式配置"""
    palette: list[str] | None = Field(default=None, description="颜色调色板")
    backgroundColor: str | None = Field(default="#fff", description="背景色")


class DimensionsSchema(BaseModel):
    """图表尺寸配置"""
    width: int = Field(default=600, description="图表宽度")
    height: int = Field(default=400, description="图表高度")


class TitleSchema(BaseModel):
    """标题配置"""
    title: str = Field(default="", description="图表标题")
    axisXTitle: str = Field(default="", description="X 轴标题")
    axisYTitle: str = Field(default="", description="Y 轴标题")
```

- [ ] **Step 5: 实现 ChartDef 和注册表 (charts/__init__.py)**

```python
from collections.abc import Callable
from dataclasses import dataclass


@dataclass
class ChartDef:
    """图表定义"""
    name: str
    description: str
    schema: type
    render: Callable[[dict], str]
    annotations: dict | None = None


ALL_CHARTS: list[ChartDef] = []
CHART_MAP: dict[str, ChartDef] = {}


def register(chart: ChartDef) -> ChartDef:
    ALL_CHARTS.append(chart)
    CHART_MAP[chart.name] = chart
    return chart
```

- [ ] **Step 6: 实现 engine.py**

```python
import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt

from deepclaw.middleware.chart.charts import CHART_MAP
from deepclaw.middleware.chart.utils import save_chart_to_workspace, setup_chinese_font


_chinese_font: str | None = None


def _get_font() -> str:
    global _chinese_font
    if _chinese_font is None:
        _chinese_font = setup_chinese_font()
    return _chinese_font


def render_chart(chart_type: str, params: dict) -> str:
    chart_def = CHART_MAP.get(chart_type)
    if not chart_def:
        raise ValueError(f"未知图表类型: {chart_type}")
    validated = chart_def.schema(**params)
    plt.rcParams["font.sans-serif"] = [_get_font()]
    plt.rcParams["axes.unicode_minus"] = False
    return chart_def.render(validated.model_dump())
```

- [ ] **Step 7: 写 engine 测试**

```python
# tests/chart/test_engine.py
from deepclaw.middleware.chart import charts
from deepclaw.middleware.chart.engine import render_chart


def test_register_and_render():
    """验证注册表和工作流"""
    assert len(charts.ALL_CHARTS) > 0
```

- [ ] **Step 8: 运行测试**

```bash
uv run pytest tests/chart/test_engine.py -v
```

Expected: PASS

- [ ] **Step 9: 提交**

```bash
git add pyproject.toml deepclaw/middleware/chart/ tests/chart/
git commit -m "feat: add chart middleware foundation layer"
```

---

### Task 2: 实现全部 9 种图表

每张图表 = 一个文件，导出 `chart()` 函数返回 `ChartDef`。所有图表共享相同的模板模式。

**Files:**
- Create: `deepclaw/middleware/chart/charts/bar.py`
- Create: `deepclaw/middleware/chart/charts/line.py`
- Create: `deepclaw/middleware/chart/charts/pie.py`
- Create: `deepclaw/middleware/chart/charts/column.py`
- Create: `deepclaw/middleware/chart/charts/scatter.py`
- Create: `deepclaw/middleware/chart/charts/area.py`
- Create: `deepclaw/middleware/chart/charts/histogram.py`
- Create: `deepclaw/middleware/chart/charts/funnel.py`
- Create: `deepclaw/middleware/chart/charts/radar.py`
- Create: `tests/chart/test_charts.py`

- [ ] **Step 1: 实现 bar.py**

```python
import matplotlib.pyplot as plt
import pandas as pd
from pydantic import BaseModel, Field

from deepclaw.middleware.chart.charts import ChartDef, register
from deepclaw.middleware.chart.utils import save_chart_to_workspace


class BarSchema(BaseModel):
    """柱状图参数"""
    data: list[dict] = Field(..., description="数据，每项含 category/value/group")
    group: bool = Field(default=False, description="是否分组")
    stack: bool = Field(default=True, description="是否堆叠")
    width: int = Field(default=600, description="图表宽度")
    height: int = Field(default=400, description="图表高度")
    title: str = Field(default="", description="图表标题")
    axisXTitle: str = Field(default="", description="X 轴标题")
    axisYTitle: str = Field(default="", description="Y 轴标题")


def render(params: dict) -> str:
    df = pd.DataFrame(params["data"])
    fig, ax = plt.subplots(figsize=(params["width"] / 100, params["height"] / 100))
    if "group" in df.columns and params.get("group", False):
        pivot = df.pivot(index="category", columns="group", values="value")
        pivot.plot(kind="barh", ax=ax, stacked=params.get("stack", True))
    else:
        ax.barh(df["category"], df["value"])
    ax.set_xlabel(params.get("axisXTitle", ""))
    ax.set_ylabel(params.get("axisYTitle", ""))
    ax.set_title(params.get("title", ""))
    fig.tight_layout()
    return save_chart_to_workspace(fig)


@register
def chart() -> ChartDef:
    return ChartDef(
        name="generate_bar_chart",
        description="生成水平柱状图，适合比较不同类别的数值大小",
        schema=BarSchema,
        render=render,
    )
```

- [ ] **Step 2-9: 按相同模式实现 line.py, pie.py, column.py, scatter.py, area.py, histogram.py, funnel.py, radar.py**

line.py:
```python
class LineSchema(BaseModel):
    data: list[dict] = Field(..., description="数据，每项含 time/value/group")


def render(params: dict) -> str:
    df = pd.DataFrame(params["data"])
    fig, ax = plt.subplots(figsize=(params["width"] / 100, params["height"] / 100))
    if "group" in df.columns:
        for g, grp in df.groupby("group"):
            ax.plot(grp["time"], grp["value"], marker="o", label=g)
        ax.legend()
    else:
        ax.plot(df["time"], df["value"], marker="o")
    ax.set_xlabel(params.get("axisXTitle", ""))
    ax.set_ylabel(params.get("axisYTitle", ""))
    ax.set_title(params.get("title", ""))
    fig.tight_layout()
    return save_chart_to_workspace(fig)
```

pie.py:
```python
class PieSchema(BaseModel):
    data: list[dict] = Field(..., description="数据，每项含 category/value")
    innerRadius: float = Field(default=0, ge=0, le=1, description="内径比率，>0 时为环形图")


def render(params: dict) -> str:
    df = pd.DataFrame(params["data"])
    fig, ax = plt.subplots(figsize=(params["width"] / 100, params["height"] / 100))
    wedges, texts, autotexts = ax.pie(
        df["value"], labels=df["category"], autopct="%1.1f%%",
        pctdistance=0.85,
        wedgeprops=dict(width=1 - params.get("innerRadius", 0)),
    )
    ax.set_title(params.get("title", ""))
    fig.tight_layout()
    return save_chart_to_workspace(fig)
```

column.py:
```python
class ColumnSchema(BaseModel):
    data: list[dict] = Field(..., description="数据，每项含 category/value/group")
    group: bool = Field(default=True)
    stack: bool = Field(default=False)


def render(params: dict) -> str:
    df = pd.DataFrame(params["data"])
    fig, ax = plt.subplots(figsize=(params["width"] / 100, params["height"] / 100))
    if "group" in df.columns and params.get("group", False):
        pivot = df.pivot(index="category", columns="group", values="value")
        pivot.plot(kind="bar", ax=ax, stacked=params.get("stack", False))
    else:
        ax.bar(df["category"], df["value"])
    ax.set_xlabel(params.get("axisXTitle", ""))
    ax.set_ylabel(params.get("axisYTitle", ""))
    ax.set_title(params.get("title", ""))
    fig.tight_layout()
    return save_chart_to_workspace(fig)
```

scatter.py:
```python
class ScatterSchema(BaseModel):
    data: list[dict] = Field(..., description="数据，每项含 x/y/group")


def render(params: dict) -> str:
    df = pd.DataFrame(params["data"])
    fig, ax = plt.subplots(figsize=(params["width"] / 100, params["height"] / 100))
    if "group" in df.columns:
        for g, grp in df.groupby("group"):
            ax.scatter(grp["x"], grp["y"], label=g, alpha=0.7)
        ax.legend()
    else:
        ax.scatter(df["x"], df["y"], alpha=0.7)
    ax.set_xlabel(params.get("axisXTitle", ""))
    ax.set_ylabel(params.get("axisYTitle", ""))
    ax.set_title(params.get("title", ""))
    fig.tight_layout()
    return save_chart_to_workspace(fig)
```

area.py:
```python
class AreaSchema(BaseModel):
    data: list[dict] = Field(..., description="数据，每项含 time/value/group")


def render(params: dict) -> str:
    df = pd.DataFrame(params["data"])
    fig, ax = plt.subplots(figsize=(params["width"] / 100, params["height"] / 100))
    if "group" in df.columns:
        pivot = df.pivot(index="time", columns="group", values="value")
        pivot.plot.area(ax=ax, alpha=0.5)
    else:
        ax.fill_between(range(len(df)), df["value"], alpha=0.3)
        ax.plot(range(len(df)), df["value"], marker="o")
        ax.set_xticks(range(len(df)))
        ax.set_xticklabels(df["time"])
    ax.set_xlabel(params.get("axisXTitle", ""))
    ax.set_ylabel(params.get("axisYTitle", ""))
    ax.set_title(params.get("title", ""))
    fig.tight_layout()
    return save_chart_to_workspace(fig)
```

histogram.py:
```python
class HistogramSchema(BaseModel):
    data: list[float] | list[dict] = Field(..., description="数值列表或含 value 字段的对象列表")
    bins: int = Field(default=10, description="分箱数量")


def render(params: dict) -> str:
    values = [d["value"] if isinstance(d, dict) else d for d in params["data"]]
    fig, ax = plt.subplots(figsize=(params["width"] / 100, params["height"] / 100))
    ax.hist(values, bins=params.get("bins", 10), edgecolor="white", alpha=0.7)
    ax.set_xlabel(params.get("axisXTitle", ""))
    ax.set_ylabel(params.get("axisYTitle", ""))
    ax.set_title(params.get("title", ""))
    fig.tight_layout()
    return save_chart_to_workspace(fig)
```

funnel.py:
```python
class FunnelSchema(BaseModel):
    data: list[dict] = Field(..., description="数据，每项含 stage/value")


def render(params: dict) -> str:
    df = pd.DataFrame(params["data"])
    fig, ax = plt.subplots(figsize=(params["width"] / 100, params["height"] / 100))
    values = df["value"].values
    stages = df["stage"].values
    max_val = values[0]
    for i, (stage, val) in enumerate(zip(stages, values)):
        width = val / max_val
        ax.barh(i, width, height=0.6, color=plt.cm.Blues(0.3 + 0.7 * (1 - i / len(values))))
        ax.text(width / 2, i, f"{stage}: {val}", ha="center", va="center")
    ax.set_yticks(range(len(values)))
    ax.set_yticklabels(stages)
    ax.invert_yaxis()
    ax.set_xlim(0, 1)
    ax.set_title(params.get("title", ""))
    ax.axis("off")
    fig.tight_layout()
    return save_chart_to_workspace(fig)
```

radar.py:
```python
import numpy as np


class RadarSchema(BaseModel):
    data: list[dict] = Field(..., description="数据，每项含 item/score/group")


def render(params: dict) -> str:
    df = pd.DataFrame(params["data"])
    fig, ax = plt.subplots(figsize=(params["width"] / 100, params["height"] / 100), subplot_kw=dict(polar=True))
    items = df["item"].unique()
    angles = np.linspace(0, 2 * np.pi, len(items), endpoint=False).tolist()
    angles += angles[:1]
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(items)
    if "group" in df.columns:
        for g, grp in df.groupby("group"):
            values = grp.set_index("item").reindex(items)["score"].fillna(0).tolist()
            values += values[:1]
            ax.plot(angles, values, marker="o", label=g)
            ax.fill(angles, values, alpha=0.1)
        ax.legend()
    else:
        values = df.set_index("item").reindex(items)["score"].fillna(0).tolist()
        values += values[:1]
        ax.plot(angles, values, marker="o")
        ax.fill(angles, values, alpha=0.1)
    ax.set_title(params.get("title", ""))
    fig.tight_layout()
    return save_chart_to_workspace(fig)
```

- [ ] **Step 10: 编写图表测试**

```python
# tests/chart/test_charts.py
import json
from pathlib import Path

import pytest

from deepclaw.middleware.chart.charts import ALL_CHARTS
from deepclaw.middleware.chart.engine import render_chart


class TestChartBasic:
    """基础图表渲染测试"""

    def test_bar_chart(self):
        url = render_chart("generate_bar_chart", {
            "data": [{"category": "A", "value": 10}, {"category": "B", "value": 20}],
            "title": "Test Bar",
        })
        assert url.startswith("/charts/")
        assert url.endswith(".png")

    def test_line_chart(self):
        url = render_chart("generate_line_chart", {
            "data": [{"time": "2020", "value": 10}, {"time": "2021", "value": 20}],
        })
        assert url.endswith(".png")

    def test_pie_chart(self):
        url = render_chart("generate_pie_chart", {
            "data": [{"category": "A", "value": 30}, {"category": "B", "value": 70}],
        })
        assert url.endswith(".png")

    def test_column_chart(self):
        url = render_chart("generate_column_chart", {
            "data": [{"category": "A", "value": 10}, {"category": "B", "value": 20}],
        })
        assert url.endswith(".png")

    def test_scatter_chart(self):
        url = render_chart("generate_scatter_chart", {
            "data": [{"x": 1, "y": 2}, {"x": 3, "y": 4}],
        })
        assert url.endswith(".png")

    def test_area_chart(self):
        url = render_chart("generate_area_chart", {
            "data": [{"time": "2020", "value": 10}, {"time": "2021", "value": 20}],
        })
        assert url.endswith(".png")

    def test_histogram_chart(self):
        url = render_chart("generate_histogram", {
            "data": [1, 2, 2, 3, 3, 3, 4, 4, 5],
        })
        assert url.endswith(".png")

    def test_funnel_chart(self):
        url = render_chart("generate_funnel_chart", {
            "data": [{"stage": "浏览", "value": 1000}, {"stage": "点击", "value": 500}, {"stage": "转化", "value": 100}],
        })
        assert url.endswith(".png")

    def test_radar_chart(self):
        url = render_chart("generate_radar_chart", {
            "data": [{"item": "速度", "score": 80}, {"item": "力量", "score": 60}, {"item": "技巧", "score": 90}],
        })
        assert url.endswith(".png")
```

- [ ] **Step 11: 运行图表测试**

```bash
uv run pytest tests/chart/ -v
```

Expected: all 9 tests PASS

- [ ] **Step 12: 提交**

```bash
git add deepclaw/middleware/chart/charts/ tests/chart/
git commit -m "feat: implement all 9 chart types"
```

---

### Task 3: Middleware 适配层 + 集成

**Files:**
- Create: `deepclaw/middleware/chart/middleware.py`
- Create: `deepclaw/middleware/chart/__init__.py`
- Modify: `deepclaw/middleware/__init__.py`
- Modify: `deepclaw/web_backend/app.py`
- Create: `tests/chart/test_middleware.py`

**Interfaces:**
- Consumes: `render_chart(chart_type, params) -> str`, `ALL_CHARTS`, `CHART_MAP`
- Produces: `ChartMiddleware` class, `/charts` static mount

- [ ] **Step 1: 实现 ChartMiddleware**

```python
from langchain.agents.middleware import AgentMiddleware, ToolCallRequest
from langchain_core.messages import ToolMessage
from langchain_core.tools import tool as langchain_tool

from deepclaw.middleware.chart.charts import ALL_CHARTS, CHART_MAP
from deepclaw.middleware.chart.engine import render_chart


class ChartMiddleware(AgentMiddleware):
    """图表生成中间件，提供 9 种图表工具"""

    @classmethod
    def get_tools(cls):
        tools = []
        for cd in ALL_CHARTS:
            @langchain_tool(name=cd.name, description=cd.description)
            def make_tool(params: dict):
                """生成图表"""
                url = render_chart(cd.name, params)
                return f"![{cd.name}]({url})"
            tools.append(make_tool)
        return tools

    async def awrap_tool_call(self, request: ToolCallRequest, handler):
        if request.tool_call["name"] in CHART_MAP:
            cd = CHART_MAP[request.tool_call["name"]]
            url = render_chart(cd.name, request.tool_call["args"])
            return ToolMessage(
                content=f"![{cd.name}]({url})",
                tool_call_id=request.tool_call["id"],
            )
        return await handler(request)
```

Wait, I need to think about this more carefully. The `@langchain_tool` decorator inside a loop with closure issue. Let me use `tool()` factory function instead, or create a factory.

Actually, the simplest approach is to use `@tool` with a proper factory:

```python
from langchain_core.tools import tool


def _make_chart_tool(cd: ChartDef):
    @tool(name=cd.name, description=cd.description)
    def chart_tool(params: dict) -> str:
        return f"![{cd.name}]({render_chart(cd.name, params)})"
    return chart_tool
```

- [ ] **Step 1: 实现 middleware.py**

```python
from langchain.agents.middleware import AgentMiddleware, ToolCallRequest
from langchain_core.messages import ToolMessage
from langchain_core.tools import tool

from deepclaw.middleware.chart.charts import ALL_CHARTS, CHART_MAP
from deepclaw.middleware.chart.engine import render_chart


def _make_chart_tool(cd):
    @tool(name=cd.name, description=cd.description)
    def chart_tool(params: dict) -> str:
        """生成图表"""
        url = render_chart(cd.name, params)
        return f"![{cd.name}]({url})"
    return chart_tool


class ChartMiddleware(AgentMiddleware):
    """图表生成中间件"""

    def get_tools(self):
        return [_make_chart_tool(cd) for cd in ALL_CHARTS]

    async def awrap_model_call(self, request, handler):
        chart_tools = self.get_tools()
        chart_tool_names = {t.name for t in chart_tools}
        extend_tools = [t for t in request.tools if t.name not in chart_tool_names]
        return await handler(request.override(tools=extend_tools + chart_tools))

    async def awrap_tool_call(self, request: ToolCallRequest, handler):
        if request.tool_call["name"] in CHART_MAP:
            cd = CHART_MAP[request.tool_call["name"]]
            url = render_chart(cd.name, request.tool_call["args"])
            return ToolMessage(
                content=f"![{cd.name}]({url})",
                tool_call_id=request.tool_call["id"],
            )
        return await handler(request)
```

- [ ] **Step 2: 实现 chart/__init__.py**

```python
"""图表生成模块。包含图表渲染引擎和 LangChain AgentMiddleware 适配。"""

from deepclaw.middleware.chart.charts import ALL_CHARTS, CHART_MAP, ChartDef, register
from deepclaw.middleware.chart.engine import render_chart
from deepclaw.middleware.chart.middleware import ChartMiddleware

__all__ = [
    "ALL_CHARTS",
    "CHART_MAP",
    "ChartDef",
    "ChartMiddleware",
    "register",
    "render_chart",
]
```

- [ ] **Step 3: 修改 middleware/__init__.py**

```python
"""langchain中间件模块"""

from deepclaw.middleware.chart import ChartMiddleware
from deepclaw.middleware.cron import CronMiddleware
from deepclaw.middleware.plan import PlanningMiddleware
from deepclaw.middleware.rag import RAGMiddleware
from deepclaw.middleware.tool_search import DeferredToolMiddleware

__all__ = [
    "ChartMiddleware",
    "CronMiddleware",
    "DeferredToolMiddleware",
    "PlanningMiddleware",
    "RAGMiddleware",
]
```

- [ ] **Step 4: 修改 app.py — 挂载 /charts 静态目录**

在 `register_frontend_routes` 之前或之后添加：

```python
def register_charts_static(app: FastAPI) -> None:
    charts_dir = workspace_path / "charts"
    charts_dir.mkdir(parents=True, exist_ok=True)
    from fastapi.staticfiles import StaticFiles

    if any(
        r.path == "/charts" for r in app.routes if hasattr(r, "path")
    ):
        return
    app.mount(
        "/charts",
        StaticFiles(directory=str(charts_dir)),
        name="charts",
    )
```

在 `create_app()` 中调用：

```python
def create_app() -> FastAPI:
    app = FastAPI(lifespan=app_lifespan)
    ...
    register_charts_static(app)  # 新增
    return app
```

- [ ] **Step 5: 写 middleware 测试**

```python
# tests/chart/test_middleware.py
from deepclaw.middleware.chart import ChartMiddleware, ALL_CHARTS


def test_middleware_tools():
    mw = ChartMiddleware()
    tools = mw.get_tools()
    assert len(tools) == len(ALL_CHARTS)
    assert all(t.name.startswith("generate_") for t in tools)
```

- [ ] **Step 6: 运行所有测试**

```bash
uv run ruff check deepclaw/middleware/chart/
uv run pytest tests/chart/ -v
```

Expected: PASS

- [ ] **Step 7: 提交**

```bash
git add deepclaw/middleware/chart/ deepclaw/middleware/__init__.py deepclaw/web_backend/app.py tests/chart/
git commit -m "feat: add ChartMiddleware and web integration"
```

---

### Task 4: 回归验证 + 文档更新

- [ ] **Step 1: 运行 ruff**

```bash
uv run ruff check .
```

- [ ] **Step 2: 运行全量测试**

```bash
uv run pytest tests -q -n auto
```

- [ ] **Step 3: 更新 AGENTS.md**

在 `deepclaw/middleware/` 描述段添加 chart 模块说明。

- [ ] **Step 4: 更新 codegraph 索引**

```bash
codegraph index --force
```

- [ ] **Step 5: 提交**

```bash
git add AGENTS.md
git commit -m "docs: update AGENTS.md with chart middleware"
```
