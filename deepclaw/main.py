import asyncio
import sys
from pathlib import Path

import uvicorn

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from deepclaw.settings import settings
from deepclaw.web_backend.app import create_app


def configure_windows_event_loop_policy() -> None:
    """Windows 下切到 SelectorEventLoop，兼容 psycopg 异步连接。"""

    if sys.platform != "win32":
        return

    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


def get_uvicorn_loop_mode() -> str:
    """Windows 避开 Proactor，其他平台保持 uvicorn 默认自动选择。"""

    if sys.platform == "win32":
        return "none"
    return "auto"


def run() -> None:
    configure_windows_event_loop_policy()
    uvicorn.run(create_app(), host=settings.HOST, port=settings.PORT, loop=get_uvicorn_loop_mode())


if __name__ == "__main__":
    run()
