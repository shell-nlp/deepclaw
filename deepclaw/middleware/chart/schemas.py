import math
from collections.abc import Iterable
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

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
    """统一图表生成参数，并按图表类型校验数据字段。"""

    chart_type: CHART_TYPES = Field(..., description="图表类型")
    data: list[dict[str, Any] | float | int] = Field(
        ...,
        min_length=1,
        max_length=1_000,
        description="""图表数据，按 chart_type 使用对应字段名：
- bar/column/pie: [{"category": "A", "value": 10, "group": "组别"}, ...]
- line/area: [{"time": "2020", "value": 10, "group": "组别"}, ...]
- scatter: [{"x": 1, "y": 2, "group": "组别"}, ...]
- radar: [{"item": "速度", "score": 80, "group": "组别"}, ...]
- funnel: [{"stage": "访问", "value": 100}, ...]
- histogram: 纯数值列表 [1, 2, 3] 或 [{"value": 1}, ...]""",
    )
    title: str = Field(default="", description="图表标题")
    width: int = Field(default=600, ge=100, le=2_400, description="图表宽度")
    height: int = Field(default=400, ge=100, le=1_800, description="图表高度")
    axisXTitle: str = Field(default="", description="X 轴标题")
    axisYTitle: str = Field(default="", description="Y 轴标题")
    group: bool = Field(default=False, description="是否使用分组数据；实际分组由 data 中的 group 字段决定")
    stack: bool | None = Field(default=None, description="是否堆叠；省略时 bar 默认堆叠、column 默认并列")
    innerRadius: float = Field(default=0, ge=0, le=1, description="内径比率 >0 时为环形图（仅 pie）")
    bins: int = Field(default=10, ge=1, le=200, description="分箱数量（仅 histogram）")

    @model_validator(mode="after")
    def validate_chart_data(self) -> "ChartSchema":
        """校验当前图表类型对应的数据契约。

        Args:
            self: 已完成基础字段解析的图表参数。
        """
        if self.stack is not None and self.chart_type not in {"bar", "column"}:
            raise ValueError("stack 仅可用于 bar 或 column")

        if self.chart_type == "histogram":
            self._validate_histogram_data()
            return self

        rows = self._require_mapping_rows()
        required_fields = {
            "bar": ("category", "value"),
            "line": ("time", "value"),
            "pie": ("category", "value"),
            "column": ("category", "value"),
            "scatter": ("x", "y"),
            "area": ("time", "value"),
            "funnel": ("stage", "value"),
            "radar": ("item", "score"),
        }
        fields = required_fields[self.chart_type]
        self._validate_required_fields(rows, fields)
        self._validate_group_consistency(rows)

        numeric_fields = {
            "bar": ("value",),
            "line": ("value",),
            "pie": ("value",),
            "column": ("value",),
            "scatter": ("x", "y"),
            "area": ("value",),
            "funnel": ("value",),
            "radar": ("score",),
        }
        self._validate_numeric_fields(rows, numeric_fields[self.chart_type])
        self._validate_chart_semantics(rows)
        return self

    def _require_mapping_rows(self) -> list[dict[str, Any]]:
        """确保非直方图数据全部为对象列表。

        Args:
            self: 当前图表参数。

        Returns:
            list[dict[str, Any]]: 经类型确认的数据行。
        """
        if not all(isinstance(row, dict) for row in self.data):
            raise ValueError(f"{self.chart_type} 的 data 必须是对象列表")
        return [row for row in self.data if isinstance(row, dict)]

    def _validate_histogram_data(self) -> None:
        """校验直方图数据为数值列表或包含 value 的对象列表。

        Args:
            self: 当前图表参数。
        """
        if all(isinstance(item, dict) for item in self.data):
            rows = [item for item in self.data if isinstance(item, dict)]
            self._validate_required_fields(rows, ("value",))
            self._validate_numeric_fields(rows, ("value",))
            return
        if all(self._is_finite_number(item) for item in self.data):
            return
        raise ValueError("histogram 的 data 必须全部是数值，或全部是包含 value 的对象")

    def _validate_required_fields(
        self,
        rows: Iterable[dict[str, Any]],
        fields: tuple[str, ...],
    ) -> None:
        """校验每一行是否具备必要字段。

        Args:
            self: 当前图表参数。
            rows: 待校验的数据行。
            fields: 每行必须包含的字段名。
        """
        for index, row in enumerate(rows):
            missing = [field for field in fields if field not in row]
            if missing:
                raise ValueError(f"data[{index}] 缺少字段: {', '.join(missing)}")
            for field in fields:
                if isinstance(row[field], str) and not row[field].strip():
                    raise ValueError(f"data[{index}].{field} 不能为空字符串")

    def _validate_group_consistency(self, rows: list[dict[str, Any]]) -> None:
        """确保分组字段在数据行中一致出现，并校验二维数据唯一性。

        Args:
            self: 当前图表参数。
            rows: 已通过必填字段校验的数据行。
        """
        grouped = ["group" in row for row in rows]
        if any(grouped) and not all(grouped):
            raise ValueError("group 字段必须在所有数据行中同时出现或同时省略")
        if not all(grouped):
            if self.group:
                raise ValueError("group=true 时，每条数据都必须提供 group 字段")
            return

        if self.chart_type in {"pie", "funnel"}:
            raise ValueError(f"{self.chart_type} 不支持 group 字段")

        for index, row in enumerate(rows):
            group = row["group"]
            if not isinstance(group, str) or not group.strip():
                raise ValueError(f"data[{index}].group 必须是非空字符串")

        dimension = {
            "bar": "category",
            "column": "category",
            "line": "time",
            "area": "time",
            "radar": "item",
        }.get(self.chart_type)
        if dimension is None:
            return
        keys = [(row[dimension], row["group"]) for row in rows]
        if len(keys) != len(set(keys)):
            raise ValueError(f"{dimension} 与 group 的组合不能重复")

    def _validate_numeric_fields(self, rows: Iterable[dict[str, Any]], fields: tuple[str, ...]) -> None:
        """校验指定字段均为有限数值。

        Args:
            self: 当前图表参数。
            rows: 待校验的数据行。
            fields: 需要校验为数值的字段名。
        """
        for index, row in enumerate(rows):
            for field in fields:
                if not self._is_finite_number(row[field]):
                    raise ValueError(f"data[{index}].{field} 必须是有限数值")

    def _validate_chart_semantics(self, rows: list[dict[str, Any]]) -> None:
        """校验各图表专属的业务约束。

        Args:
            self: 当前图表参数。
            rows: 已通过字段和数值校验的数据行。
        """
        if self.chart_type == "pie":
            values = [float(row["value"]) for row in rows]
            if any(value < 0 for value in values) or not any(value > 0 for value in values):
                raise ValueError("pie 的 value 必须非负，且至少存在一个正数")
        if self.chart_type == "funnel":
            values = [float(row["value"]) for row in rows]
            if any(value < 0 for value in values) or not any(value > 0 for value in values):
                raise ValueError("funnel 的 value 必须非负，且至少存在一个正数")

    @staticmethod
    def _is_finite_number(value: object) -> bool:
        """判断值是否为可用于绘图的有限数值。

        Args:
            value: 待判断的值。

        Returns:
            bool: 值为有限非布尔数值时返回真。
        """
        if isinstance(value, bool):
            return False
        try:
            return math.isfinite(float(value))
        except (TypeError, ValueError):
            return False
