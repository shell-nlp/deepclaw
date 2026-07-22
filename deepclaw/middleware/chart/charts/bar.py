import matplotlib.pyplot as plt
import pandas as pd

from deepclaw.middleware.chart.utils import (
    build_axis_title,
    configure_value_axis,
    format_compact_number,
    get_value_scale,
    save_chart_to_workspace,
)


def render(params: dict) -> str:
    """渲染水平柱状图。

    Args:
        params: 已通过参数校验的图表参数。

    Returns:
        str: 已保存图表的访问地址。
    """
    df = pd.DataFrame(params["data"])
    value_scale, value_unit = get_value_scale(df["value"])
    df["value"] = df["value"] / value_scale
    fig, ax = plt.subplots(figsize=(params["width"] / 100, params["height"] / 100))
    stacked = params["stack"] if params["stack"] is not None else True
    if "group" in df.columns:
        pivot = df.pivot(index="category", columns="group", values="value")
        pivot = pivot.loc[pivot.sum(axis=1).sort_values(ascending=False).index]
        pivot.plot(kind="barh", ax=ax, stacked=stacked)
    else:
        sorted_df = df.sort_values("value", ascending=False)
        ax.barh(sorted_df["category"], sorted_df["value"])
    for container in ax.containers:
        ax.bar_label(
            container,
            labels=[format_compact_number(value * value_scale) for value in container.datavalues],
            label_type="edge",
            padding=3,
        )
    ax.invert_yaxis()
    configure_value_axis(ax.xaxis)
    ax.set_xlabel(build_axis_title(params.get("axisXTitle", ""), value_unit))
    ax.set_ylabel(params.get("axisYTitle", ""))
    ax.set_title(params.get("title", ""))
    fig.tight_layout()
    return save_chart_to_workspace(fig)
