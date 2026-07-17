import matplotlib.pyplot as plt
import pandas as pd

from deepclaw.middleware.chart.utils import save_chart_to_workspace


def render(params: dict) -> str:
    """渲染水平柱状图。

    Args:
        params: 已通过参数校验的图表参数。

    Returns:
        str: 已保存图表的访问地址。
    """
    df = pd.DataFrame(params["data"])
    fig, ax = plt.subplots(figsize=(params["width"] / 100, params["height"] / 100))
    stacked = params["stack"] if params["stack"] is not None else True
    if "group" in df.columns:
        pivot = df.pivot(index="category", columns="group", values="value")
        pivot.plot(kind="barh", ax=ax, stacked=stacked)
    else:
        ax.barh(df["category"], df["value"])
    ax.set_xlabel(params.get("axisXTitle", ""))
    ax.set_ylabel(params.get("axisYTitle", ""))
    ax.set_title(params.get("title", ""))
    fig.tight_layout()
    return save_chart_to_workspace(fig)
