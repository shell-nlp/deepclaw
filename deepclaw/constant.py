import os
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent

# 源码检出时等于仓库根目录；pip 安装后等于 site-packages 之类的只读位置。
ROOT_DIR = PACKAGE_DIR.parent

HOME_ENV_NAME = "DEEPCLAW_HOME"


def is_source_checkout() -> bool:
    """判断当前是否运行在本仓库的源码检出中。

    Args:
        无。

    Returns:
        仓库根目录同时存在 pyproject.toml 与 deepclaw 包目录时返回 True。
    """

    return (ROOT_DIR / "pyproject.toml").is_file() and (ROOT_DIR / "deepclaw").is_dir()


def resolve_home_path() -> Path:
    """解析运行期数据根目录。

    优先级：DEEPCLAW_HOME 环境变量 > 源码检出内的仓库 .deepclaw > 用户主目录 .deepclaw。
    pip 安装后 ROOT_DIR 位于 site-packages，不允许往那里写运行期数据，因此回退到主目录。

    Args:
        无。

    Returns:
        运行期数据根目录，不做创建。
    """

    configured = os.environ.get(HOME_ENV_NAME, "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    if is_source_checkout():
        return ROOT_DIR / ".deepclaw"
    return Path.home() / ".deepclaw"


# 宿主侧路径（Windows / Linux / macOS 通用，由 pathlib.Path 自动处理分隔符）
HOME_PATH = resolve_home_path()
WORKSPACE_PATH = HOME_PATH / "workspace"

# 构建 wheel 时由 setup.py 把 frontend/out 复制到这里，供安装态静态托管。
BUNDLED_FRONTEND_PATH = PACKAGE_DIR / "web_static" / "frontend"


def resolve_frontend_path() -> Path | None:
    """定位前端静态导出目录。

    源码检出优先使用 frontend/out，wheel 安装回退到包内副本。

    Args:
        无。

    Returns:
        存在的导出目录；都不存在时返回 None。
    """

    for candidate in (ROOT_DIR / "frontend" / "out", BUNDLED_FRONTEND_PATH):
        if candidate.is_dir():
            return candidate
    return None


# 沙箱容器内路径（OpenSandbox 是 Linux 容器，路径必须保持 POSIX 风格，
# 千万不要换成 host 路径，否则容器内部访问不到）。
SANDBOX_SHARED_WORKSPACE = "/shared_workspace"
SANDBOX_HOME = "/.deepclaw"
SANDBOX_USER_WORKSPACE = f"{SANDBOX_HOME}/workspace"
SANDBOX_USER_SKILLS = f"{SANDBOX_USER_WORKSPACE}/skills"
SANDBOX_USER_AGENTS = f"{SANDBOX_USER_WORKSPACE}/AGENTS.md"
SANDBOX_SHARED_SKILLS = f"{SANDBOX_SHARED_WORKSPACE}/skills"
SANDBOX_SHARED_AGENTS = f"{SANDBOX_SHARED_WORKSPACE}/AGENTS.md"

# Agent 抽象的虚拟路径，由 StoreBackend 路由，与宿主 OS 无关
AGENT_VIRTUAL_MEMORIES = "/memories"
AGENT_VIRTUAL_PREFERENCES = f"{AGENT_VIRTUAL_MEMORIES}/preferences.md"
