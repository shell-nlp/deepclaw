from io import BytesIO
from textwrap import fill

import matplotlib.font_manager as fm
import matplotlib.pyplot as plt
from loguru import logger

from deepclaw.middleware.chart.storage import (
    CHART_BUCKET_NAME,
    CHART_OBJECT_PREFIX,
    save_chart_png,
)
from deepclaw.settings import settings


def wrap_chart_label(value: object, width: int = 12) -> str:
    """按可读宽度换行文本，避免长类目挤占绘图区。

    Args:
        value: 待换行的标签内容。
        width: 每行最多保留的字符数。

    Returns:
        str: 保留完整文本的换行标签。
    """
    return fill(str(value), width=width, break_long_words=True, break_on_hyphens=False)


def place_chart_legend(
    axis: plt.Axes,
    *,
    handles=None,
    labels=None,
    offset: float = 1.02,
) -> None:
    """将图例移到绘图区右侧，并按图例行数扩展画布。

    Args:
        axis: 需要放置图例的坐标轴。
        handles: 图例图元；省略时取自坐标轴。
        labels: 图例文本；省略时取自坐标轴。
        offset: 图例相对绘图区右边缘的横向偏移。
    """
    if handles is None or labels is None:
        handles, labels = axis.get_legend_handles_labels()
    if not labels:
        return
    labels = [wrap_chart_label(label, 20) for label in labels]
    fig = axis.figure
    width, height = fig.get_size_inches()
    legend_width = max(len(line) for label in labels for line in label.splitlines()) * 0.12 + 0.8
    legend_rows = sum(len(label.splitlines()) for label in labels)
    fig.set_size_inches(
        min(24, max(6, width) + legend_width),
        max(height, min(18, 1.4 + legend_rows * 0.23)),
    )
    axis.legend(
        handles,
        labels,
        title=None,
        loc="upper left",
        bbox_to_anchor=(offset, 1),
        borderaxespad=0,
    )


def fit_category_ticks(axis: plt.Axes, *, time_axis: bool = False) -> None:
    """类别刻度换行；密集时间轴只抽稀刻度，保留全部数据点。

    Args:
        axis: 需要调整刻度显示方式的坐标轴。
        time_axis: 是否为时间轴；为真时按序抽稀，否则换行显示类目。
    """
    ticks = axis.get_xticks()
    labels = [label.get_text() for label in axis.get_xticklabels()]
    if not labels:
        return
    if time_axis:
        data_min, data_max = axis.dataLim.intervalx
        pairs = [(tick, label) for tick, label in zip(ticks, labels) if data_min <= tick <= data_max]
        if pairs:
            ticks, labels = zip(*pairs)
        stride = max(1, (len(labels) + 11) // 12)
        indices = list(range(0, len(labels), stride))
        if indices[-1] != len(labels) - 1:
            indices[-1] = len(labels) - 1
        axis.set_xticks(
            [ticks[index] for index in indices],
            [labels[index] for index in indices],
            rotation=45,
            ha="right",
        )
        spacing = 0.65
        count = len(indices)
    else:
        axis.set_xticks(ticks, [wrap_chart_label(label, 6) for label in labels], rotation=0)
        spacing = 0.8
        count = len(labels)
    fig = axis.figure
    fig.set_size_inches(
        max(fig.get_figwidth(), min(24, 2 + count * spacing)),
        max(fig.get_figheight(), 4.5),
    )


def finalize_chart_layout(
    fig: plt.Figure,
    *,
    vertical_label_axes: tuple[plt.Axes, ...] = (),
    horizontal_label_axes: tuple[plt.Axes, ...] = (),
) -> None:
    """为数据标签预留坐标轴空间并完成画布布局。

    统一负责最小可读画布、标题换行、最终布局和数值标签碰撞处理。
    碰撞时只隐藏重复的数值标注，图元与原始数据保持不变。

    Args:
        fig: 待调整布局的 Matplotlib 图形对象。
        vertical_label_axes: 数据标签位于数据点上方的坐标轴，扩展 y 轴范围。
        horizontal_label_axes: 数据标签位于水平条末端的坐标轴，扩展 x 轴范围。
    """
    for axis in vertical_label_axes:
        axis.margins(y=0.15)
    for axis in horizontal_label_axes:
        axis.margins(x=0.15)
    fig.set_size_inches(max(6, fig.get_figwidth()), max(4, fig.get_figheight()))
    for axis in fig.axes:
        axis.title.set_text(wrap_chart_label(axis.get_title(), max(12, int(fig.get_figwidth() * 7))))
    fig.tight_layout()
    # 静态图密集标注允许省略，曲线、点和饼图图元始终保留。
    labels = [
        label
        for axis in fig.axes
        for label in axis.texts
        if label.get_gid() == "chart-value-label"
    ]
    if labels:
        fig.canvas.draw()
        renderer = fig.canvas.get_renderer()
        occupied = []
        for label in labels:
            box = label.get_window_extent(renderer).expanded(1.08, 1.15)
            visible = not any(box.overlaps(other) for other in occupied)
            label.set_visible(visible)
            if visible:
                occupied.append(box)


def format_number(value: float) -> str:
    """将数值格式化为标准数值文本。

    Args:
        value: 待格式化的数值。

    Returns:
        str: 普通数值或科学计数法文本。
    """
    return f"{float(value):.12g}"


def setup_chinese_font() -> str:
    """自动探测可用的中文字体名称，找不到时回退到 DejaVu Sans。

    Returns:
        str: 可用字体名称。
    """
    font_candidates = [
        "SimHei",
        "Microsoft YaHei",
        "PingFang SC",
        "Noto Sans CJK SC",
        "WenQuanYi Zen Hei",
        "WenQuanYi Micro Hei",
        "DejaVu Sans",
    ]
    available = {f.name for f in fm.fontManager.ttflist}
    for name in font_candidates:
        if name in available:
            logger.info("使用中文字体: {}", name)
            return name
    logger.warning("未找到中文字体，回退到 DejaVu Sans")
    return "DejaVu Sans"


def _resolve_chart_public_url() -> str:
    """解析图表公开地址前缀并兼容完整 URL 配置。

    Returns:
        str: 拼接图表路径前使用的地址前缀。
    """
    configured_url = settings.CHART_PUBLIC_URL.strip()
    if not configured_url:
        return ""
    if configured_url.startswith(("http://", "https://")):
        return configured_url.rstrip("/")
    return f"{settings.LOCAL_HOST.rstrip('/')}/{configured_url.lstrip('/')}"


def save_chart_to_workspace(fig: plt.Figure) -> str:
    """将 matplotlib 图表保存到对象存储，并返回可访问地址。

    Args:
        fig: 待保存的 matplotlib 图形对象。

    Returns:
        str: 图表的可访问 URL 路径。
    """
    buffer = BytesIO()
    try:
        # 渲染器已完成最终布局与碰撞处理，保存时不再移动图元。
        fig.savefig(
            buffer,
            format="png",
            dpi=150,
            bbox_inches="tight",
            facecolor="white",
        )
    finally:
        plt.close(fig)
    file_name = save_chart_png(buffer.getvalue())
    logger.info(
        "图表已保存: {}/{}",
        CHART_BUCKET_NAME,
        f"{CHART_OBJECT_PREFIX}/{file_name}",
    )
    base_path = f"/charts/{file_name}"
    public_url = _resolve_chart_public_url()
    return f"{public_url}{base_path}" if public_url else base_path
