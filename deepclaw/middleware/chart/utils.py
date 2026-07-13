import socket
import uuid
from pathlib import Path

import matplotlib.font_manager as fm
import matplotlib.pyplot as plt
from loguru import logger

from deepclaw.constant import workspace_path
from deepclaw.settings import settings

_CHARTS_DIR: Path | None = None


def _get_charts_dir() -> Path:
    """获取图表输出目录，延迟初始化。"""
    global _CHARTS_DIR
    if _CHARTS_DIR is None:
        _CHARTS_DIR = workspace_path / "charts"
        _CHARTS_DIR.mkdir(parents=True, exist_ok=True)
    return _CHARTS_DIR


def setup_chinese_font() -> str:
    """自动探测可用的中文字体名称，找不到时回退到 DejaVu Sans。

    Returns
    -------
    str
        可用字体名称
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


def _get_default_public_url() -> str:
    """获取本机局域网 IP 作为默认公网地址。

    Returns
    -------
    str
        格式为 http://<ip>:<port>
    """
    try:
        host_ip = "127.0.0.1"
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.1)
        s.connect(("10.255.255.255", 1))
        host_ip = s.getsockname()[0]
        s.close()
    except Exception:
        host_ip = socket.gethostbyname(socket.gethostname())
    return f"http://{host_ip}:{settings.PORT}"


def save_chart_to_workspace(fig: plt.Figure) -> str:
    """将 matplotlib 图表保存到工作区并返回 URL。

    Parameters
    ----------
    fig : plt.Figure
        matplotlib 图形对象

    Returns
    -------
    str
        图表的可访问 URL 路径
    """
    file_name = f"{uuid.uuid4().hex}.png"
    file_path = _get_charts_dir() / file_name
    fig.savefig(file_path, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    logger.info("图表已保存: {}", file_path)
    base_path = f"/charts/{file_name}"
    public_url = settings.CHART_PUBLIC_URL
    if not public_url:
        public_url = _get_default_public_url()
    return f"{public_url.rstrip('/')}{base_path}"
