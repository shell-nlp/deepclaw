from pathlib import Path
from typing import Any

from loguru import logger

from deepclaw.constant import WORKSPACE_PATH

# 技能在虚拟文件系统中的挂载点，必须与 create_deep_agent 的 skills 源保持一致。
SKILLS_VIRTUAL_ROOT = "/workspace/skills"
# 技能在宿主机上的存放目录。
SKILLS_DIR = WORKSPACE_PATH / "skills"


def user_namespace_factory(runtime: Any) -> tuple[str, ...]:
    """动态生成用户 namespace。

    Args:
        runtime: 当前 Agent 运行时，优先读取运行时身份信息。
    """
    server_info = getattr(runtime, "server_info", None)
    user = getattr(server_info, "user", None)
    identity = getattr(user, "identity", None)
    user_id = str(identity) if identity else "default"
    return ("filesystem", user_id)


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


async def sync_skills_store(skills_dir: Path, store: Any) -> int:
    """把本地技能目录全量同步到 LangGraph Store。

    先删除旧的技能条目再上传，保证 store 内容与本地目录一致；写入时复用
    user_namespace_factory，与 deep agent 读取技能时的命名空间严格相同。

    Args:
        skills_dir: 本地技能根目录。
        store: LangGraph Store 实例。

    Returns:
        成功写入的文件数量。
    """
    from deepagents.backends.store import StoreBackend

    backend = StoreBackend(namespace=user_namespace_factory, store=store)
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
