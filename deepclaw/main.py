import asyncio
import socket
import sys
import threading
import time
from pathlib import Path

import uvicorn
from loguru import logger

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


def get_local_ip_addresses() -> list[str]:
    """获取本机可用于访问服务的 IPv4 地址。

    Args:
        无。

    Returns:
        去重后的本机 IPv4 地址列表，默认出口地址排在前面。
    """
    candidates: list[str] = []

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.connect(("8.8.8.8", 80))
            candidates.append(probe.getsockname()[0])
    except OSError:
        pass

    try:
        _, _, host_ips = socket.gethostbyname_ex(socket.gethostname())
    except OSError:
        host_ips = []
    candidates.extend(host_ips)

    addresses: list[str] = []
    for ip in candidates:
        if ip.startswith("127.") or ip in addresses:
            continue
        addresses.append(ip)
    return addresses


def log_startup_urls() -> None:
    """记录服务启动后可访问的地址。

    Args:
        无。
    """
    port = settings.PORT
    port_suffix = "" if port == 80 else f":{port}"
    host = settings.HOST

    urls = [f"http://localhost{port_suffix}"]
    if host in {"0.0.0.0", "::", ""}:
        urls.extend(f"http://{ip}{port_suffix}" for ip in get_local_ip_addresses())
    elif host not in {"127.0.0.1", "localhost", "::1"}:
        urls.append(f"http://{host}{port_suffix}")

    logger.info(
        "服务已启动，监听 {}:{}，可访问地址：\n{}",
        host,
        port,
        "\n".join(f"    {url}" for url in urls),
    )


def log_urls_when_server_ready(server: uvicorn.Server) -> None:
    """等待端口绑定成功后记录访问地址。

    端口被占用时 uvicorn 会直接退出，此时不输出误导性的访问地址。

    Args:
        server: 正在运行的 uvicorn 服务器实例。
    """
    while not server.should_exit:
        if server.started:
            log_startup_urls()
            return
        time.sleep(0.1)


def run() -> None:
    configure_windows_event_loop_policy()
    config = uvicorn.Config(
        create_app(),
        host=settings.HOST,
        port=settings.PORT,
        loop=get_uvicorn_loop_mode(),
    )
    server = uvicorn.Server(config)
    threading.Thread(
        target=log_urls_when_server_ready,
        args=(server,),
        daemon=True,
    ).start()
    server.run()


if __name__ == "__main__":
    run()
