# ChartMiddleware 设计文档

## 背景

参考 [antvis/mcp-server-chart](https://github.com/antvis/mcp-server-chart)（TypeScript 实现的 MCP Chart Server），在 deepclaw 中实现 Python 版本的图表生成能力，作为 AgentMiddleware 内置工具接入 LangChain Agent。

## 目标

1. 提供 9 种基础图表类型的生成能力：bar, line, pie, column, scatter, area, histogram, funnel, radar
2. 使用 matplotlib 本地渲染，输出为 PNG 图片，返回可访问的 URL
3. 核心渲染逻辑与中间件层严格**解耦**，后续可低成本发布为独立 MCP Server

## 架构

```
┌─────────────────────────────────────────────────────────┐
│                  消费者层 (Adapter)                        │
│  ┌─────────────────────┐  ┌──────────────────────────┐   │
│  │ ChartMiddleware     │  │ MCP Server (未来)         │   │
│  │ (AgentMiddleware)   │  │ (from fastmcp / mcp)     │   │
│  └────────┬────────────┘  └───────────┬──────────────┘   │
└───────────┼───────────────────────────┼──────────────────┘
            │                           │
            ▼                           ▼
┌─────────────────────────────────────────────────────────┐
│                核心层 (deepclaw/middleware/chart/)        │
│                                                          │
│  charts/__init__.py    ← 注册表 {name: ChartDef}         │
│  charts/bar.py         ← ChartDef(schema, render, tool)  │
│  charts/line.py                                          │
│  charts/pie.py                                           │
│  ...                                                     │
│  engine.py             ← render_chart() 渲染引擎          │
│  schemas.py            ← Pydantic 公共字段                │
│  utils.py              ← 中文字体、颜色、文件 I/O          │
└─────────────────────────────────────────────────────────┘
```

### 核心层（纯业务，零框架依赖）

```python
# ChartDef 是每个图表类型的标准描述
@dataclass
class ChartDef:
    name: str                     # 工具名, e.g. "generate_bar_chart"
    description: str              # 工具描述
    schema: type[BaseModel]       # Pydantic 入参模型
    render: Callable              # 渲染函数 (data, params) → str (URL)
    annotations: dict | None = None
```

每个 `charts/*.py` 文件导出 `def chart() -> ChartDef`。

`engine.py` 的 `render_chart(chart_type, params)` 根据注册表找到 ChartDef，执行 render，保存到 `workspace_path/charts/{uuid}.png`。

### 适配层（消费者）

```python
# middleware.py — 仅 ~40 行，负责:
# 1. 注册所有 chart 为 LangChain tools
# 2. awrap_tool_call 中拦截 chart 工具名，调用 engine.render_chart()
# 3. 返回 ToolMessage

class ChartMiddleware(AgentMiddleware):
    name = "chart"
    
    async def get_tools(self):
        return [create_langchain_tool(cd) for cd in ALL_CHARTS]
    
    async def awrap_tool_call(self, request, handler):
        if request.tool_call["name"] in CHART_TOOL_NAMES:
            url = render_chart(...)
            return ToolMessage(content=markdown_image(url))
        return await handler(request)
```

## URL 生成策略

- 保存路径: `.deepclaw/workspace/charts/{uuid}.png`
- Web 场景: 在 `app.py` 挂载 `StaticFiles("/charts", ...)`，返回 `/charts/{uuid}.png`
- CLI 场景: 返回 `file://` 绝对路径
- 工具返回值: 同时包含 `![chart](url)` markdown + JSON spec

## 初始支持的图表

| 工具名 | 图表类型 | 数据字段 |
|---|---|---|
| `generate_bar_chart` | 柱状图 | category, value[, group] |
| `generate_line_chart` | 折线图 | time, value[, group] |
| `generate_pie_chart` | 饼图 | category, value |
| `generate_column_chart` | 条形图 | category, value[, group, stack] |
| `generate_scatter_chart` | 散点图 | x, y[, group] |
| `generate_area_chart` | 面积图 | time, value[, group] |
| `generate_histogram` | 直方图 | value |
| `generate_funnel_chart` | 漏斗图 | stage, value |
| `generate_radar_chart` | 雷达图 | item, score[, group] |

## 非功能需求

- 渲染引擎无强制依赖 langchain / langgraph
- 新增图表类型只需在 `charts/` 下新建文件 + 在注册表注册
- 中文字体自动探测（系统字体 fallback）
- 图表样式对标 AntV 默认风格（简洁、清晰）
