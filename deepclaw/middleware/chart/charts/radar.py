import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from deepclaw.middleware.chart.utils import (
    build_axis_title,
    configure_value_axis,
    get_value_scale,
    save_chart_to_workspace,
)


def render(params: dict) -> str:
    """渲染雷达图。

    Args:
        params: 已通过参数校验的图表参数。

    Returns:
        str: 已保存图表的访问地址。
    """
    df = pd.DataFrame(params["data"])
    value_scale, value_unit = get_value_scale(df["score"])
    df["score"] = df["score"] / value_scale
    fig, ax = plt.subplots(
        figsize=(params["width"] / 100, params["height"] / 100),
        subplot_kw=dict(polar=True),
    )
    items = df["item"].unique()
    angles = np.linspace(0, 2 * np.pi, len(items), endpoint=False).tolist()
    angles += angles[:1]
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(items)
    if "group" in df.columns:
        for g, grp in df.groupby("group"):
            values = grp.set_index("item").reindex(items)["score"].fillna(0).tolist()
            values += values[:1]
            ax.plot(angles, values, marker="o", label=g)
            ax.fill(angles, values, alpha=0.1)
        ax.legend(loc="upper right", bbox_to_anchor=(1.3, 1.0))
    else:
        values = df.set_index("item").reindex(items)["score"].fillna(0).tolist()
        values += values[:1]
        ax.plot(angles, values, marker="o")
        ax.fill(angles, values, alpha=0.1)
    configure_value_axis(ax.yaxis)
    ax.set_ylabel(build_axis_title(params.get("axisYTitle", ""), value_unit), labelpad=20)
    ax.set_title(params.get("title", ""), pad=20)
    fig.tight_layout()
    return save_chart_to_workspace(fig)
