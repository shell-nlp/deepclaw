import matplotlib.pyplot as plt

from deepclaw.middleware.chart.utils import (
    build_axis_title,
    configure_value_axis,
    get_value_scale,
    save_chart_to_workspace,
)


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
    value_scale, value_unit = get_value_scale(values)
    values = [value / value_scale for value in values]
    fig, ax = plt.subplots(figsize=(params["width"] / 100, params["height"] / 100))
    ax.hist(values, bins=params.get("bins", 10), edgecolor="white", alpha=0.7)
    configure_value_axis(ax.xaxis)
    ax.set_xlabel(build_axis_title(params.get("axisXTitle", ""), value_unit))
    ax.set_ylabel(params.get("axisYTitle", ""))
    ax.set_title(params.get("title", ""))
    fig.tight_layout()
    return save_chart_to_workspace(fig)
