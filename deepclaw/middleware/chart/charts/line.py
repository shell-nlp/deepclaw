import matplotlib.pyplot as plt
import pandas as pd

from deepclaw.middleware.chart.utils import (
    format_number,
    save_chart_to_workspace,
)


def render(params: dict) -> str:
    """渲染折线图。

    Args:
        params: 已通过参数校验的图表参数。

    Returns:
        str: 已保存图表的访问地址。
    """
    df = pd.DataFrame(params["data"])
    fig, ax = plt.subplots(figsize=(params["width"] / 100, params["height"] / 100))
    if "group" in df.columns:
        for g, grp in df.groupby("group"):
            sorted_grp = grp.sort_values("time")
            ax.plot(sorted_grp["time"], sorted_grp["value"], marker="o", label=g)
        ax.legend()
    else:
        sorted_df = df.sort_values("time")
        ax.plot(sorted_df["time"], sorted_df["value"], marker="o")
    for line in ax.lines:
        for time, value in zip(line.get_xdata(), line.get_ydata()):
            ax.annotate(
                format_number(value),
                (time, value),
                textcoords="offset points",
                xytext=(0, 7),
                ha="center",
            )
    ax.set_xlabel(params.get("axisXTitle", ""))
    ax.set_ylabel(params.get("axisYTitle", ""))
    ax.set_title(params.get("title", ""))
    fig.tight_layout()
    return save_chart_to_workspace(fig)
