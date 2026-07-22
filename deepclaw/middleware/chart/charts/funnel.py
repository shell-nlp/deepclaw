import matplotlib.pyplot as plt
import pandas as pd

from deepclaw.middleware.chart.utils import format_compact_number, save_chart_to_workspace


def render(params: dict) -> str:
    """渲染漏斗图。

    Args:
        params: 已通过参数校验的图表参数。

    Returns:
        str: 已保存图表的访问地址。
    """
    df = pd.DataFrame(params["data"])
    fig, ax = plt.subplots(figsize=(params["width"] / 100, params["height"] / 100))
    values = df["value"].values
    stages = df["stage"].values
    max_val = values.max()
    n = len(values)
    colors = plt.cm.Blues([0.3 + 0.7 * (1 - i / n) for i in range(n)])
    for i, (stage, val) in enumerate(zip(stages, values)):
        width = val / max_val
        ax.barh(i, width, height=0.6, color=colors[i])
        ax.text(
            width / 2,
            i,
            f"{stage}: {format_compact_number(val)}",
            ha="center",
            va="center",
            fontsize=10,
        )
    ax.set_yticks(range(n))
    ax.set_yticklabels(stages)
    ax.invert_yaxis()
    ax.set_xlim(0, 1)
    ax.set_title(params.get("title", ""))
    ax.axis("off")
    fig.tight_layout()
    return save_chart_to_workspace(fig)
