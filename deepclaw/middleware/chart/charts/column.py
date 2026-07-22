import matplotlib.pyplot as plt
import pandas as pd

from deepclaw.middleware.chart.utils import (
    build_axis_title,
    configure_value_axis,
    get_value_scale,
    save_chart_to_workspace,
)


def render(params: dict) -> str:
    """渲染垂直条形图。

    Args:
        params: 已通过参数校验的图表参数。

    Returns:
        str: 已保存图表的访问地址。
    """
    df = pd.DataFrame(params["data"])
    value_scale, value_unit = get_value_scale(df["value"])
    df["value"] = df["value"] / value_scale
    fig, ax = plt.subplots(figsize=(params["width"] / 100, params["height"] / 100))
    stacked = params["stack"] if params["stack"] is not None else False
    if "group" in df.columns:
        pivot = df.pivot(index="category", columns="group", values="value")
        pivot.plot(kind="bar", ax=ax, stacked=stacked)
    else:
        ax.bar(df["category"], df["value"])
    ax.set_xlabel(params.get("axisXTitle", ""))
    configure_value_axis(ax.yaxis)
    ax.set_ylabel(build_axis_title(params.get("axisYTitle", ""), value_unit))
    ax.set_title(params.get("title", ""))
    fig.tight_layout()
    return save_chart_to_workspace(fig)
