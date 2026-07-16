from typing import Any, Callable

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import FancyBboxPatch

from deepclaw.middleware.chart.schemas import ChartSchema, CHART_TYPE_DESCRIPTIONS  # noqa: F401
from deepclaw.middleware.chart.utils import save_chart_to_workspace

ChartDef = dict[str, Any]

_RenderFn = Callable[[dict], str]


def _render_bar(data: dict) -> str:
    """渲染水平柱状图。"""
    fig, ax = plt.subplots(figsize=(data["width"] / 100, data["height"] / 100))
    raw = data["data"]
    has_group = data["group"] and any("group" in d for d in raw)
    stack = data["stack"]

    if has_group:
        groups = sorted({d["group"] for d in raw})
        categories = sorted({d["category"] for d in raw})
        x = np.arange(len(categories))
        width = 0.8 / len(groups)
        if stack:
            bottoms = [0] * len(categories)
            for g in groups:
                vals = []
                for c in categories:
                    match = [d for d in raw if d["category"] == c and d["group"] == g]
                    vals.append(match[0]["value"] if match else 0)
                ax.barh(categories, vals, left=bottoms, label=g)
                bottoms = [b + v for b, v in zip(bottoms, vals)]
        else:
            for i, g in enumerate(groups):
                vals = []
                for c in categories:
                    match = [d for d in raw if d["category"] == c and d["group"] == g]
                    vals.append(match[0]["value"] if match else 0)
                pos = x + (i - len(groups) / 2 + 0.5) * width
                ax.barh(categories, vals, height=width, left=pos, label=g)
        ax.legend()
    else:
        categories = [d["category"] for d in raw]
        values = [d["value"] for d in raw]
        ax.barh(categories, values)

    ax.set_title(data["title"])
    if data["axisXTitle"]:
        ax.set_xlabel(data["axisXTitle"])
    if data["axisYTitle"]:
        ax.set_ylabel(data["axisYTitle"])
    plt.tight_layout()
    return save_chart_to_workspace(fig)


def _render_line(data: dict) -> str:
    """渲染折线图。"""
    fig, ax = plt.subplots(figsize=(data["width"] / 100, data["height"] / 100))
    raw = data["data"]
    has_group = any("group" in d for d in raw)

    if has_group:
        groups = sorted({d["group"] for d in raw})
        for g in groups:
            points = [d for d in raw if d["group"] == g]
            times = [d["time"] for d in points]
            values = [d["value"] for d in points]
            ax.plot(times, values, marker="o", label=g)
        ax.legend()
    else:
        times = [d["time"] for d in raw]
        values = [d["value"] for d in raw]
        ax.plot(times, values, marker="o")

    ax.set_title(data["title"])
    if data["axisXTitle"]:
        ax.set_xlabel(data["axisXTitle"])
    if data["axisYTitle"]:
        ax.set_ylabel(data["axisYTitle"])
    plt.tight_layout()
    return save_chart_to_workspace(fig)


def _render_pie(data: dict) -> str:
    """渲染饼图/环形图。"""
    fig, ax = plt.subplots(figsize=(data["width"] / 100, data["height"] / 100))
    raw = data["data"]
    labels = [d["category"] for d in raw]
    values = [d["value"] for d in raw]
    inner = data["innerRadius"]
    wedges, texts, autotexts = ax.pie(
        values,
        labels=labels,
        autopct="%1.1f%%",
        startangle=90,
        wedgeprops={"width": 1 - inner} if inner > 0 else None,
        pctdistance=0.85 if inner > 0 else 0.6,
    )
    if inner > 0:
        ax.set_title(data["title"], pad=20)
    else:
        ax.set_title(data["title"])
    plt.tight_layout()
    return save_chart_to_workspace(fig)


def _render_column(data: dict) -> str:
    """渲染垂直条形图。"""
    fig, ax = plt.subplots(figsize=(data["width"] / 100, data["height"] / 100))
    raw = data["data"]
    has_group = any("group" in d for d in raw)
    stack = data["stack"]

    if has_group:
        groups = sorted({d["group"] for d in raw})
        categories = sorted({d["category"] for d in raw})
        x = np.arange(len(categories))
        width = 0.8 / len(groups)
        for i, g in enumerate(groups):
            vals = []
            for c in categories:
                match = [d for d in raw if d["category"] == c and d["group"] == g]
                vals.append(match[0]["value"] if match else 0)
            if stack:
                if i == 0:
                    bottoms = [0] * len(categories)
                    ax.bar(x, vals, width, label=g)
                else:
                    ax.bar(x, vals, width, bottom=bottoms, label=g)
                    bottoms = [b + v for b, v in zip(bottoms, vals)]
            else:
                pos = x + (i - len(groups) / 2 + 0.5) * width
                ax.bar(pos, vals, width, label=g)
        ax.legend()
    else:
        categories = [d["category"] for d in raw]
        values = [d["value"] for d in raw]
        ax.bar(categories, values)

    ax.set_xticks(range(len(categories)))
    ax.set_xticklabels(categories)
    ax.set_title(data["title"])
    if data["axisXTitle"]:
        ax.set_xlabel(data["axisXTitle"])
    if data["axisYTitle"]:
        ax.set_ylabel(data["axisYTitle"])
    plt.tight_layout()
    return save_chart_to_workspace(fig)


def _render_scatter(data: dict) -> str:
    """渲染散点图。"""
    fig, ax = plt.subplots(figsize=(data["width"] / 100, data["height"] / 100))
    raw = data["data"]
    has_group = any("group" in d for d in raw)

    if has_group:
        groups = sorted({d["group"] for d in raw})
        for g in groups:
            points = [d for d in raw if d["group"] == g]
            xs = [d["x"] for d in points]
            ys = [d["y"] for d in points]
            ax.scatter(xs, ys, label=g)
        ax.legend()
    else:
        xs = [d["x"] for d in raw]
        ys = [d["y"] for d in raw]
        ax.scatter(xs, ys)

    ax.set_title(data["title"])
    if data["axisXTitle"]:
        ax.set_xlabel(data["axisXTitle"])
    if data["axisYTitle"]:
        ax.set_ylabel(data["axisYTitle"])
    plt.tight_layout()
    return save_chart_to_workspace(fig)


def _render_area(data: dict) -> str:
    """渲染面积图。"""
    fig, ax = plt.subplots(figsize=(data["width"] / 100, data["height"] / 100))
    raw = data["data"]
    has_group = any("group" in d for d in raw)

    if has_group:
        groups = sorted({d["group"] for d in raw})
        for g in groups:
            points = [d for d in raw if d["group"] == g]
            times = [d["time"] for d in points]
            values = [d["value"] for d in points]
            ax.fill_between(times, values, alpha=0.5, label=g)
        ax.legend()
    else:
        times = [d["time"] for d in raw]
        values = [d["value"] for d in raw]
        ax.fill_between(times, values, alpha=0.5)

    ax.set_title(data["title"])
    if data["axisXTitle"]:
        ax.set_xlabel(data["axisXTitle"])
    if data["axisYTitle"]:
        ax.set_ylabel(data["axisYTitle"])
    plt.tight_layout()
    return save_chart_to_workspace(fig)


def _render_histogram(data: dict) -> str:
    """渲染直方图。"""
    fig, ax = plt.subplots(figsize=(data["width"] / 100, data["height"] / 100))
    raw = data["data"]
    bins = data["bins"]

    if raw and isinstance(raw[0], dict):
        values = [d["value"] for d in raw]
    elif raw and isinstance(raw[0], (int, float)):
        values = list(raw)
    else:
        values = []

    ax.hist(values, bins=bins, edgecolor="white")
    ax.set_title(data["title"])
    if data["axisXTitle"]:
        ax.set_xlabel(data["axisXTitle"])
    if data["axisYTitle"]:
        ax.set_ylabel(data["axisYTitle"])
    plt.tight_layout()
    return save_chart_to_workspace(fig)


def _render_funnel(data: dict) -> str:
    """渲染漏斗图。"""
    fig, ax = plt.subplots(figsize=(data["width"] / 100, data["height"] / 100))
    raw = data["data"]
    stages = [d["stage"] for d in raw]
    values = [d["value"] for d in raw]
    max_val = max(values) if values else 1

    for i, (stage, val) in enumerate(zip(stages, values)):
        width = val / max_val
        left = (1 - width) / 2
        rect = FancyBboxPatch(
            (left, i), width, 0.7,
            boxstyle="round,pad=0.02",
            facecolor=plt.cm.Blues(0.3 + 0.7 * (1 - i / len(stages))),
            edgecolor="gray",
        )
        ax.add_patch(rect)
        ax.text(0.5, i + 0.35, f"{stage}: {val}", ha="center", va="center", fontsize=10)

    ax.set_xlim(0, 1)
    ax.set_ylim(0, len(stages))
    ax.set_title(data["title"])
    ax.axis("off")
    plt.tight_layout()
    return save_chart_to_workspace(fig)


def _render_radar(data: dict) -> str:
    """渲染雷达图。"""
    fig, ax = plt.subplots(
        figsize=(data["width"] / 100, data["height"] / 100),
        subplot_kw={"projection": "polar"},
    )
    raw = data["data"]
    has_group = any("group" in d for d in raw)

    if has_group:
        groups = sorted({d["group"] for d in raw})
        for g in groups:
            points = [d for d in raw if d["group"] == g]
            items = [d["item"] for d in points]
            scores = [d["score"] for d in points]
            angles = np.linspace(0, 2 * np.pi, len(items), endpoint=False).tolist()
            scores_closed = scores + [scores[0]]
            angles_closed = angles + [angles[0]]
            ax.plot(angles_closed, scores_closed, "o-", label=g)
            ax.fill(angles_closed, scores_closed, alpha=0.1)
        ax.legend()
    else:
        items = [d["item"] for d in raw]
        scores = [d["score"] for d in raw]
        angles = np.linspace(0, 2 * np.pi, len(items), endpoint=False).tolist()
        scores_closed = scores + [scores[0]]
        angles_closed = angles + [angles[0]]
        ax.plot(angles_closed, scores_closed, "o-")
        ax.fill(angles_closed, scores_closed, alpha=0.1)
        ax.set_xticks(angles)
        ax.set_xticklabels(items)

    ax.set_title(data["title"], pad=20)
    plt.tight_layout()
    return save_chart_to_workspace(fig)


CHART_RENDERERS: dict[str, _RenderFn] = {
    "bar": _render_bar,
    "line": _render_line,
    "pie": _render_pie,
    "column": _render_column,
    "scatter": _render_scatter,
    "area": _render_area,
    "histogram": _render_histogram,
    "funnel": _render_funnel,
    "radar": _render_radar,
}

__all__ = [
    "CHART_RENDERERS",
    "ChartDef",
    "ChartSchema",
]
