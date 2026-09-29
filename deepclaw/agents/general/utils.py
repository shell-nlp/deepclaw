from pathlib import Path
from typing import Any

from loguru import logger

from deepclaw.constant import WORKSPACE_PATH

# 技能在虚拟文件系统中的挂载点，必须与 create_deep_agent 的 skills 源保持一致。
SKILLS_VIRTUAL_ROOT = "/workspace/skills"
# 技能在宿主机上的存放目录。
SKILLS_DIR = WORKSPACE_PATH / "skills"
# 运行时取不到用户身份时使用的兜底用户 ID。
FALLBACK_USER_ID = "default"


def user_id_from_runtime(runtime: Any) -> str:
    """从运行时身份中提取用户 ID。

    Args:
        runtime: 当前 Agent 运行时。

    Returns:
        用户 ID；运行时没有身份信息时返回兜底值。
    """
    server_info = getattr(runtime, "server_info", None)
    user = getattr(server_info, "user", None)
    identity = getattr(user, "identity", None)
    return str(identity) if identity else FALLBACK_USER_ID


def user_namespace(user_id: str | None = None) -> tuple[str, ...]:
    """按用户 ID 计算文件系统 Store 命名空间。

    Args:
        user_id: 用户 ID；为空时使用兜底用户。

    Returns:
        Store 命名空间元组。
    """
    return ("filesystem", user_id or FALLBACK_USER_ID)


def user_namespace_factory(runtime: Any) -> tuple[str, ...]:
    """动态生成用户 namespace。

    Args:
        runtime: 当前 Agent 运行时，优先读取运行时身份信息。
    """
    return user_namespace(user_id_from_runtime(runtime))


def _iter_skill_files(skills_dir: Path) -> list[tuple[str, bytes]]:
    """收集技能目录下的文件并映射成虚拟路径。

    Args:
        skills_dir: 本地技能根目录。

    Returns:
        (虚拟路径, 文件内容) 列表，按虚拟路径排序。
    """
    if not skills_dir.exists():
        return []

    files: list[tuple[str, bytes]] = []
    for file_path in sorted(skills_dir.rglob("*")):
        if not file_path.is_file() or "__pycache__" in file_path.parts:
            continue
        relative_path = file_path.relative_to(skills_dir).as_posix()
        files.append((f"{SKILLS_VIRTUAL_ROOT}/{relative_path}", file_path.read_bytes()))
    return files


def _local_skill_names(skills_dir: Path) -> list[str]:
    """列出本地一级技能目录名。

    Args:
        skills_dir: 本地技能根目录。

    Returns:
        排序后的技能目录名列表。
    """
    if not skills_dir.exists():
        return []
    return sorted(path.name for path in skills_dir.iterdir() if path.is_dir())


async def _skills_up_to_date(backend: Any, skills_dir: Path) -> bool:
    """判断 store 中的技能是否与本地一致。

    只比较一级技能目录名：技能的新增与删除都会改变目录集合，而改动已有技能内容属于
    手动操作，需要重启或再次增删技能才会重新同步。

    Args:
        backend: 已绑定用户命名空间的 StoreBackend。
        skills_dir: 本地技能根目录。

    Returns:
        一致时返回 True。
    """
    listing = await backend.als(SKILLS_VIRTUAL_ROOT)
    if listing.error:
        return False
    remote_names = sorted(
        Path(entry["path"].rstrip("/")).name
        for entry in (listing.entries or [])
        if entry["path"].endswith("/")
    )
    return remote_names == _local_skill_names(skills_dir)


async def sync_skills_store(skills_dir: Path, store: Any, user_id: str) -> int:
    """把本地技能目录同步到指定用户命名空间的 LangGraph Store。

    写入命名空间与 deep agent 读取技能时严格一致（都由当前用户身份决定）；目录集合
    未变化时直接跳过，避免每轮运行都重写全部技能。

    Args:
        skills_dir: 本地技能根目录。
        store: LangGraph Store 实例。
        user_id: 技能写入的用户 ID，决定 Store 命名空间。

    Returns:
        本次实际写入的文件数量；无需同步时为 0。
    """
    from deepagents.backends.store import StoreBackend

    namespace = user_namespace(user_id)
    backend = StoreBackend(namespace=lambda _runtime: namespace, store=store)
    if await _skills_up_to_date(backend, skills_dir):
        return 0

    await backend.adelete(SKILLS_VIRTUAL_ROOT)
    files = _iter_skill_files(skills_dir)
    if not files:
        logger.info("本地技能目录为空，已清空 store 中的技能条目：{}", skills_dir)
        return 0

    responses = await backend.aupload_files(files)
    failures = [item for item in responses if item.error]
    for item in failures:
        logger.warning("技能写入 store 失败 {}：{}", item.path, item.error)
    logger.info(
        "技能已同步到 store：成功 {} 个，失败 {} 个",
        len(responses) - len(failures),
        len(failures),
    )
    return len(responses) - len(failures)
