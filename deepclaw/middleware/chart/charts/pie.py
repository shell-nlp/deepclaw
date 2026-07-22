import matplotlib.pyplot as plt
import pandas as pd

from deepclaw.middleware.chart.utils import format_compact_number, save_chart_to_workspace


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
        autopct="%1.1f%%",
        pctdistance=0.85,
        wedgeprops=dict(width=1 - inner_radius) if inner_radius > 0 else {},
    )
    legend_labels = [
        f"{category}（{format_compact_number(value)}）"
        for category, value in zip(df["category"], df["value"])
    ]
    ax.legend(wedges, legend_labels, title="数据项", loc="center left", bbox_to_anchor=(1, 0.5))
    if inner_radius > 0:
        ax.add_artist(plt.Circle((0, 0), inner_radius, color="white"))
    ax.set_title(params.get("title", ""))
    fig.tight_layout()
    return save_chart_to_workspace(fig)
