import matplotlib.pyplot as plt
import pandas as pd

from deepclaw.middleware.chart.utils import (
    finalize_chart_layout,
    format_number,
    place_chart_legend,
    save_chart_to_workspace,
)


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
    total = df["value"].sum()
    wedges, texts, autotexts = ax.pie(
        df["value"],
        autopct=lambda percentage: (
            f"{percentage:.1f}%" if percentage >= 3 and inner_radius <= 0.75 else ""
        ),
        pctdistance=(1 + inner_radius) / 2,
        wedgeprops=dict(width=1 - inner_radius) if inner_radius > 0 else {},
    )
    for text in autotexts:
        if text.get_text():
            text.set_gid("chart-value-label")
    labels = [
        f"{row.category}: {format_number(row.value)} ({row.value / total * 100:.3g}%)"
        for row in df.itertuples()
    ]
    place_chart_legend(ax, handles=wedges, labels=labels)
    ax.set_title(params.get("title", ""))
    finalize_chart_layout(fig)
    return save_chart_to_workspace(fig)
