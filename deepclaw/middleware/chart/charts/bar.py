import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from deepclaw.middleware.chart.utils import (
    format_number,
    save_chart_to_workspace,
)


def _is_rate_group(group: object) -> bool:
    """判断分组名称是否表示比例类指标。

    Args:
        group: 图表数据中的分组名称。

    Returns:
        bool: 分组表示比例、百分比或占比时返回真。
    """
    group_name = str(group)
    return any(keyword in group_name for keyword in ("率", "百分比", "%", "占比"))


def render(params: dict) -> str:
    """渲染水平柱状图。

    Args:
        params: 已通过参数校验的图表参数。

    Returns:
        str: 已保存图表的访问地址。
    """
    df = pd.DataFrame(params["data"])
    fig, ax = plt.subplots(figsize=(params["width"] / 100, params["height"] / 100))
    if "group" in df.columns:
        pivot = df.pivot(index="category", columns="group", values="value")
        rate_groups = [group for group in pivot.columns if _is_rate_group(group)]
        value_groups = [group for group in pivot.columns if group not in rate_groups]
        if len(rate_groups) == 1 and value_groups:
            pivot = pivot.loc[pivot[value_groups].sum(axis=1).sort_values(ascending=False).index]
            positions = np.arange(len(pivot))
            bar_height = 0.8 / (len(value_groups) + 1)
            for index, group in enumerate(value_groups):
                bars = ax.barh(
                    positions + (index - len(value_groups) / 2) * bar_height,
                    pivot[group].fillna(0),
                    height=bar_height,
                    label=group,
                )
                ax.bar_label(bars, labels=[format_number(value) for value in bars.datavalues], padding=3)
            rate_ax = ax.twiny()
            rate_bars = rate_ax.barh(
                positions + len(value_groups) / 2 * bar_height,
                pivot[rate_groups[0]].fillna(0),
                height=bar_height,
                color="tab:orange",
                label=rate_groups[0],
            )
            rate_ax.bar_label(
                rate_bars,
                labels=[format_number(value) for value in rate_bars.datavalues],
                padding=3,
            )
            ax.set_yticks(positions, pivot.index)
            ax.set_xlabel(" / ".join(value_groups))
            ax.set_ylabel(params.get("axisXTitle", ""))
            rate_ax.set_xlabel(rate_groups[0])
            handles = [*ax.containers, *rate_ax.containers]
            ax.legend(handles=handles, loc="upper left", bbox_to_anchor=(1.02, 1))
        else:
            pivot = pivot.loc[pivot.sum(axis=1).sort_values(ascending=False).index]
            stacked = params["stack"] if params["stack"] is not None else False
            pivot.plot(kind="barh", ax=ax, stacked=stacked)
            for container in ax.containers:
                ax.bar_label(
                    container,
                    labels=[format_number(value) for value in container.datavalues],
                    label_type="center" if stacked else "edge",
                    padding=3,
                )
    else:
        sorted_df = df.sort_values("value", ascending=False)
        bars = ax.barh(sorted_df["category"], sorted_df["value"])
        ax.bar_label(bars, labels=[format_number(value) for value in bars.datavalues], padding=3)
    ax.invert_yaxis()
    if not ("group" in df.columns and len(rate_groups) == 1 and value_groups):
        ax.set_xlabel(params.get("axisXTitle", ""))
        ax.set_ylabel(params.get("axisYTitle", ""))
    ax.set_title(params.get("title", ""))
    fig.tight_layout()
    return save_chart_to_workspace(fig)
