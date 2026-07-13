from typing import Literal

from pydantic import BaseModel, Field

CHART_TYPES = Literal[
    "bar", "line", "pie", "column", "scatter",
    "area", "histogram", "funnel", "radar",
]

CHART_TYPE_DESCRIPTIONS = {
    "bar": "水平柱状图，比较不同类别的数值大小",
    "line": "折线图，展示数据随时间的变化趋势",
    "pie": "饼图/环形图，展示各部分占总体的比例",
    "column": "垂直条形图，比较分类数据之间的数值差异",
    "scatter": "散点图，展示两个变量之间的关系",
    "area": "面积图，展示数量随时间的变化幅度",
    "histogram": "直方图，展示数据分布频率",
    "funnel": "漏斗图，展示各阶段转化流失情况",
    "radar": "雷达图，展示多维度指标对比",
}


class ChartSchema(BaseModel):
    """统一图表生成参数

    支持 9 种图表类型，共用基础参数，少量图表专用参数放在可选字段。
    """

    chart_type: CHART_TYPES = Field(..., description="图表类型")
    data: list[dict] | list[float] | list[int] = Field(
        ...,
        description="""图表数据，按 chart_type 使用对应字段名：
- bar/column/pie/funnel: [{"category": "A", "value": 10, "group": "组别"}, ...]
- line/area: [{"time": "2020", "value": 10, "group": "组别"}, ...]
- scatter: [{"x": 1, "y": 2, "group": "组别"}, ...]
- radar: [{"item": "速度", "score": 80, "group": "组别"}, ...]
- histogram: 纯数值列表 [1, 2, 3] 或 [{"value": 1}, ...]""",
    )
    title: str = Field(default="", description="图表标题")
    width: int = Field(default=600, description="图表宽度")
    height: int = Field(default=400, description="图表高度")
    axisXTitle: str = Field(default="", description="X 轴标题")
    axisYTitle: str = Field(default="", description="Y 轴标题")
    group: bool = Field(default=False, description="是否分组（bar/column/scatter 可用）")
    stack: bool = Field(default=True, description="是否堆叠（bar 默认 true，column 请传 false）")
    innerRadius: float = Field(default=0, ge=0, le=1, description="内径比率 >0 时为环形图（仅 pie）")
    bins: int = Field(default=10, description="分箱数量（仅 histogram）")
