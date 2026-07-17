import matplotlib.pyplot as plt
import pandas as pd

from deepclaw.middleware.chart.utils import save_chart_to_workspace


def render(params: dict) -> str:
    """渲染饼图或环形图。

    Args:
        params: 已通过参数校验的图表参数。

    Returns:
        str: 已保存图表的访问地址。
    """
    df = pd.DataFrame(params["data"])
    fig, ax = plt.subplots(figsize=(params["width"] / 100, params["height"] / 100))
    inner_radius = params.get("innerRadius", 0)
    wedges, texts, autotexts = ax.pie(
        df["value"],
        labels=df["category"],
        autopct="%1.1f%%",
        pctdistance=0.85,
        wedgeprops=dict(width=1 - inner_radius) if inner_radius > 0 else {},
    )
    if inner_radius > 0:
        ax.add_artist(plt.Circle((0, 0), inner_radius, color="white"))
    ax.set_title(params.get("title", ""))
    fig.tight_layout()
    return save_chart_to_workspace(fig)
