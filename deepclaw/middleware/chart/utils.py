import time
import uuid
from collections.abc import Iterable
from pathlib import Path

import matplotlib.font_manager as fm
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.ticker import FuncFormatter
from loguru import logger

from deepclaw.constant import workspace_path
from deepclaw.settings import settings

_CHARTS_DIR: Path | None = None


def get_value_scale(values: Iterable[float]) -> tuple[float, str]:
    """根据数值量级确定展示单位。

    Args:
        values: 待判断量级的数值序列。

    Returns:
        tuple[float, str]: 数值换算系数及其中文单位。
    """
    max_abs_value = max((abs(float(value)) for value in values), default=0)
    for threshold, unit in ((100_000_000, "亿"), (1_000_000, "百万"), (10_000, "万")):
        if max_abs_value >= threshold:
            return threshold, unit
    return 1, ""


def format_number(value: float) -> str:
    """将数值格式化为非科学计数法文本。

    Args:
        value: 待格式化的数值。

    Returns:
        str: 不含科学计数法的数值文本。
    """
    return np.format_float_positional(float(value), trim="-")


def format_compact_number(value: float) -> str:
    """按单个数值的量级格式化可读文本。

    Args:
        value: 待格式化的原始数值。

    Returns:
        str: 带有万、百万或亿单位的数值文本。
    """
    value_scale, value_unit = get_value_scale((value,))
    return f"{format_number(value / value_scale)}{value_unit}"


def format_axis_tick(value: float, _position: float) -> str:
    """格式化数值轴刻度。

    Args:
        value: 数值轴刻度值。
        _position: 数值轴刻度位置。

    Returns:
        str: 不含科学计数法的刻度文本。
    """
    return format_number(value)


def configure_value_axis(axis: object) -> None:
    """为数值轴配置非科学计数法刻度。

    Args:
        axis: Matplotlib 的数值轴对象。
    """
    axis.set_major_formatter(FuncFormatter(format_axis_tick))


def build_axis_title(title: str, unit: str, default_title: str = "数值") -> str:
    """为轴标题追加自动换算后的单位。

    Args:
        title: 调用方传入的轴标题。
        unit: 自动选择的展示单位。
        default_title: 缺少轴标题时使用的默认名称。

    Returns:
        str: 含单位的轴标题。
    """
    return f"{title or default_title}（{unit}）" if unit else title


def _get_charts_dir() -> Path:
    """获取图表输出目录，并在首次调用时创建。

    Returns:
        Path: 图表文件输出目录。
    """
    global _CHARTS_DIR
    if _CHARTS_DIR is None:
        _CHARTS_DIR = workspace_path / "charts"
        _CHARTS_DIR.mkdir(parents=True, exist_ok=True)
    return _CHARTS_DIR


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


def cleanup_chart_files(charts_dir: Path | None = None) -> None:
    """清理过期图表，并限制保留文件数量。

    Args:
        charts_dir: 待清理的图表目录，默认使用工作区图表目录。
    """
    directory = charts_dir or _get_charts_dir()
    now = time.time()
    retention_seconds = settings.CHART_RETENTION_HOURS * 3_600
    retained: list[tuple[float, Path]] = []
    for file_path in directory.glob("*.png"):
        try:
            modified_at = file_path.stat().st_mtime
            if now - modified_at > retention_seconds:
                file_path.unlink()
                continue
            retained.append((modified_at, file_path))
        except OSError as error:
            logger.warning("清理图表文件失败: path={}, error={}", file_path, repr(error))

    retained.sort(key=lambda item: item[0], reverse=True)
    for _, file_path in retained[settings.CHART_MAX_FILES:]:
        try:
            file_path.unlink()
        except OSError as error:
            logger.warning("清理超额图表文件失败: path={}, error={}", file_path, repr(error))


def save_chart_to_workspace(fig: plt.Figure) -> str:
    """将 matplotlib 图表保存到工作区，并返回可访问地址。

    Args:
        fig: 待保存的 matplotlib 图形对象。

    Returns:
        str: 图表的可访问 URL 路径。
    """
    charts_dir = _get_charts_dir()
    file_name = f"{uuid.uuid4().hex}.png"
    file_path = charts_dir / file_name
    try:
        fig.savefig(file_path, dpi=150, bbox_inches="tight", facecolor="white")
    finally:
        plt.close(fig)
    cleanup_chart_files(charts_dir)
    logger.info("图表已保存: {}", file_path)
    base_path = f"/charts/{file_name}"
    public_url = settings.CHART_PUBLIC_URL
    return f"{public_url.rstrip('/')}{base_path}" if public_url else base_path
