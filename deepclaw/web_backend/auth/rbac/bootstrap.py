import asyncio
import threading

from loguru import logger

from deepclaw.web_backend.auth.rbac.adapter import bootstrap_policy_store, read_default_policy_file
from deepclaw.web_backend.auth.rbac.enforcer import resolve_rbac_paths
from deepclaw.web_backend.auth.rbac.store import get_rbac_policy_store


def _run_sync(coro) -> None:
    """执行初始化协程，兼容「已有事件循环」和「无事件循环」两种调用场景。

    Args:
        coro: 待执行的初始化协程。
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        asyncio.run(coro)
        return

    error: list[BaseException] = []

    def runner() -> None:
        """在新线程的独立事件循环中执行协程。

        Args:
            无。
        """
        try:
            asyncio.run(coro)
        except BaseException as exc:  # noqa: BLE001 - 需要把异常传回调用线程
            error.append(exc)

    thread = threading.Thread(target=runner)
    thread.start()
    thread.join()
    if error:
        raise error[0]


def bootstrap_rbac_policy() -> None:
    """在服务启动前建表并在空库写入基础策略。

    Args:
        无。

    Raises:
        RuntimeError: 建表或写入基础策略失败时抛出。
    """
    _, policy_path = resolve_rbac_paths()
    if not policy_path.is_file():
        raise RuntimeError(f"RBAC 基础策略文件不存在: {policy_path}")
    policies, roles = read_default_policy_file(policy_path)
    try:
        _run_sync(bootstrap_policy_store(get_rbac_policy_store(), policies, roles))
    except Exception as exc:  # noqa: BLE001 - 启动阶段需要显式失败
        raise RuntimeError(f"RBAC 基础策略初始化失败: {exc}") from exc
    logger.info("RBAC 基础策略已就绪: policies={} roles={}", len(policies), len(roles))
