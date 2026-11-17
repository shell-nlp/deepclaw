import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from deepclaw.middleware.chart.utils import (
    finalize_chart_layout,
    place_chart_legend,
    save_chart_to_workspace,
    wrap_chart_label,
)


def render(params: dict) -> str:
    """渲染雷达图。

    Args:
        params: 已通过参数校验的图表参数。

    Returns:
        str: 已保存图表的访问地址。
    """
    df = pd.DataFrame(params["data"])
    fig, ax = plt.subplots(
        figsize=(params["width"] / 100, params["height"] / 100),
        subplot_kw=dict(polar=True),
    )
    items = df["item"].unique()
    angles = np.linspace(0, 2 * np.pi, len(items), endpoint=False).tolist()
    angles += angles[:1]
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels([wrap_chart_label(item, 6) for item in items])
    ax.tick_params(axis="x", pad=14)
    for angle, label in zip(angles, ax.get_xticklabels()):
        label.set_horizontalalignment(
            "left" if np.cos(angle) > 0.1 else "right" if np.cos(angle) < -0.1 else "center"
        )
    fig.set_size_inches(max(8, fig.get_figwidth()), max(7, fig.get_figheight()))
    if "group" in df.columns:
        for g, grp in df.groupby("group"):
            values = grp.set_index("item").reindex(items)["score"].fillna(0).tolist()
            values += values[:1]
            ax.plot(angles, values, marker="o", label=g)
            ax.fill(angles, values, alpha=0.1)
        place_chart_legend(ax, offset=1.35)
    else:
        values = df.set_index("item").reindex(items)["score"].fillna(0).tolist()
        values += values[:1]
        ax.plot(angles, values, marker="o")
        ax.fill(angles, values, alpha=0.1)
    ax.set_title(params.get("title", ""), pad=20)
    finalize_chart_layout(fig)
    return save_chart_to_workspace(fig)
