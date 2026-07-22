import matplotlib.pyplot as plt
import pandas as pd

from deepclaw.middleware.chart.utils import (
    build_axis_title,
    configure_value_axis,
    get_value_scale,
    save_chart_to_workspace,
)


def render(params: dict) -> str:
    """渲染散点图。

    Args:
        params: 已通过参数校验的图表参数。

    Returns:
        str: 已保存图表的访问地址。
    """
    df = pd.DataFrame(params["data"])
    x_scale, x_unit = get_value_scale(df["x"])
    y_scale, y_unit = get_value_scale(df["y"])
    df["x"] = df["x"] / x_scale
    df["y"] = df["y"] / y_scale
    fig, ax = plt.subplots(figsize=(params["width"] / 100, params["height"] / 100))
    if "group" in df.columns:
        for g, grp in df.groupby("group"):
            ax.scatter(grp["x"], grp["y"], label=g, alpha=0.7)
        ax.legend()
    else:
        ax.scatter(df["x"], df["y"], alpha=0.7)
    configure_value_axis(ax.xaxis)
    configure_value_axis(ax.yaxis)
    ax.set_xlabel(build_axis_title(params.get("axisXTitle", ""), x_unit, "X 值"))
    ax.set_ylabel(build_axis_title(params.get("axisYTitle", ""), y_unit, "Y 值"))
    ax.set_title(params.get("title", ""))
    fig.tight_layout()
    return save_chart_to_workspace(fig)
