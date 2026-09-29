import asyncio
from pathlib import Path

from langgraph.store.memory import InMemoryStore

from deepclaw.agents.general.utils import (
    SKILLS_VIRTUAL_ROOT,
    sync_skills_store,
    user_namespace_factory,
)


def _write_demo_skill(skills_dir: Path) -> None:
    """在技能目录下写入一个最小技能包。

    Args:
        skills_dir: 本地技能根目录。
    """
    (skills_dir / "demo" / "scripts").mkdir(parents=True)
    (skills_dir / "demo" / "SKILL.md").write_text("# demo", encoding="utf-8")
    (skills_dir / "demo" / "scripts" / "run.py").write_text(
        "print(1)", encoding="utf-8"
    )


def test_sync_skills_store_writes_into_namespace_read_by_agent(tmp_path):
    """验证技能写入的命名空间与 deep agent 读取技能时一致，且能被 StoreBackend 读到。"""
    from deepagents.backends.store import StoreBackend

    store = InMemoryStore()
    _write_demo_skill(tmp_path)

    copied = asyncio.run(sync_skills_store(tmp_path, store))

    assert copied == 2
    keys = sorted(item.key for item in store.search(("filesystem", "default")))
    assert keys == [
        f"{SKILLS_VIRTUAL_ROOT}/demo/SKILL.md",
        f"{SKILLS_VIRTUAL_ROOT}/demo/scripts/run.py",
    ]

    backend = StoreBackend(namespace=user_namespace_factory, store=store)
    listing = backend.ls(SKILLS_VIRTUAL_ROOT)
    assert listing.error is None
    assert [entry["path"] for entry in listing.entries or []] == [
        f"{SKILLS_VIRTUAL_ROOT}/demo/"
    ]

    content = backend.read(f"{SKILLS_VIRTUAL_ROOT}/demo/SKILL.md")
    assert content.file_data["content"] == "# demo"
    assert content.file_data["encoding"] == "utf-8"


def test_sync_skills_store_replaces_previous_entries(tmp_path):
    """验证重复同步不会残留旧条目，本地删除也会同步到 store。"""
    store = InMemoryStore()
    _write_demo_skill(tmp_path)

    assert asyncio.run(sync_skills_store(tmp_path, store)) == 2
    assert asyncio.run(sync_skills_store(tmp_path, store)) == 2
    assert len(store.search(("filesystem", "default"))) == 2

    (tmp_path / "demo" / "SKILL.md").unlink()

    assert asyncio.run(sync_skills_store(tmp_path, store)) == 1
    keys = sorted(item.key for item in store.search(("filesystem", "default")))
    assert keys == [f"{SKILLS_VIRTUAL_ROOT}/demo/scripts/run.py"]
