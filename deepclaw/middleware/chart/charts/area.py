import matplotlib.pyplot as plt
import pandas as pd

from deepclaw.middleware.chart.utils import save_chart_to_workspace


def render(params: dict) -> str:
    """渲染面积图。

    Args:
        params: 已通过参数校验的图表参数。

    Returns:
        str: 已保存图表的访问地址。
    """
    df = pd.DataFrame(params["data"])
    fig, ax = plt.subplots(figsize=(params["width"] / 100, params["height"] / 100))
    if "group" in df.columns:
        pivot = df.pivot(index="time", columns="group", values="value")
        pivot.plot.area(ax=ax, alpha=0.5)
    else:
        sorted_df = df.sort_values("time")
        ax.fill_between(range(len(sorted_df)), sorted_df["value"], alpha=0.3)
        ax.plot(range(len(sorted_df)), sorted_df["value"], marker="o")
        ax.set_xticks(range(len(sorted_df)))
        ax.set_xticklabels(sorted_df["time"])
    ax.set_xlabel(params.get("axisXTitle", ""))
    ax.set_ylabel(params.get("axisYTitle", ""))
    ax.set_title(params.get("title", ""))
    fig.tight_layout()
    return save_chart_to_workspace(fig)
