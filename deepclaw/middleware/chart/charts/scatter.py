import matplotlib.pyplot as plt
import pandas as pd

from deepclaw.middleware.chart.utils import save_chart_to_workspace


def render(params: dict) -> str:
    """渲染散点图。

    Args:
        params: 已通过参数校验的图表参数。

    Returns:
        str: 已保存图表的访问地址。
    """
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
