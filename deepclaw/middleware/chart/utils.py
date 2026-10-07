from io import BytesIO

import matplotlib.font_manager as fm
import matplotlib.pyplot as plt
from loguru import logger

from deepclaw.middleware.chart.storage import (
    CHART_BUCKET_NAME,
    CHART_OBJECT_PREFIX,
    save_chart_png,
)
from deepclaw.settings import settings


def finalize_chart_layout(
    fig: plt.Figure,
    *,
    vertical_label_axes: tuple[plt.Axes, ...] = (),
    horizontal_label_axes: tuple[plt.Axes, ...] = (),
) -> None:
    """为数据标签预留坐标轴空间并完成画布布局。

    Args:
        fig: 待调整布局的 Matplotlib 图形对象。
        vertical_label_axes: 数据标签位于数据点上方的坐标轴，扩展 y 轴范围。
        horizontal_label_axes: 数据标签位于水平条末端的坐标轴，扩展 x 轴范围。
    """
    for axis in vertical_label_axes:
        axis.margins(y=0.15)
    for axis in horizontal_label_axes:
        axis.margins(x=0.15)
    fig.tight_layout()
    fig.subplots_adjust(top=0.92)


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
        # 统一兜底处理标题和坐标轴标签的画布边界。
        fig.tight_layout()
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
