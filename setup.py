"""打包构建钩子：把前端静态导出目录复制进 wheel 的包内路径。

前端构建产物位于仓库的 frontend/out，不在 deepclaw 包内。直接打包会让安装态
找不到静态资源，因此这里在标准 build_py 之后补充复制，源码检出本身不受影响。
"""

from pathlib import Path
from shutil import copytree, rmtree

from setuptools import setup
from setuptools.command.build_py import build_py as _build_py

REPO_ROOT = Path(__file__).resolve().parent
FRONTEND_OUT_DIR = REPO_ROOT / "frontend" / "out"
BUNDLED_FRONTEND_DIR = Path("deepclaw") / "web_static" / "frontend"


class BuildPyWithFrontend(_build_py):
    """在标准 Python 包构建之后追加前端静态文件。

    Args:
        无。
    """

    def run(self) -> None:
        """执行标准构建并复制前端导出目录。

        Args:
            无。
        """

        super().run()
        if not FRONTEND_OUT_DIR.is_dir():
            return
        target_dir = Path(self.build_lib) / BUNDLED_FRONTEND_DIR
        if target_dir.exists():
            rmtree(target_dir)
        copytree(FRONTEND_OUT_DIR, target_dir)


setup(cmdclass={"build_py": BuildPyWithFrontend})
