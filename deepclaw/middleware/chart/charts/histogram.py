import matplotlib.pyplot as plt

from deepclaw.middleware.chart.utils import save_chart_to_workspace


def render(params: dict) -> str:
    """渲染直方图。

    Args:
        params: 已通过参数校验的图表参数。

    Returns:
        str: 已保存图表的访问地址。
    """
    raw = params["data"]
    if raw and isinstance(raw[0], dict):
        values = [d["value"] for d in raw]
    else:
        values = list(raw)
    fig, ax = plt.subplots(figsize=(params["width"] / 100, params["height"] / 100))
    ax.hist(values, bins=params.get("bins", 10), edgecolor="white", alpha=0.7)
    ax.set_xlabel(params.get("axisXTitle", ""))
    ax.set_ylabel(params.get("axisYTitle", ""))
    ax.set_title(params.get("title", ""))
    fig.tight_layout()
    return save_chart_to_workspace(fig)
