import time
import uuid
from pathlib import Path

import matplotlib.font_manager as fm
import matplotlib.pyplot as plt
from loguru import logger

from deepclaw.constant import workspace_path
from deepclaw.settings import settings

_CHARTS_DIR: Path | None = None


def format_number(value: float) -> str:
    """将数值格式化为标准数值文本。

    Args:
        value: 待格式化的数值。

    Returns:
        str: 普通数值或科学计数法文本。
    """
    return f"{float(value):.15g}"


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
