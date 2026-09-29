import asyncio
import shutil
from pathlib import Path

from langgraph.store.memory import InMemoryStore

from deepclaw.agents.general.utils import (
    SKILLS_VIRTUAL_ROOT,
    sync_skills_store,
    user_namespace,
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


def test_sync_skills_store_writes_into_given_user_namespace(tmp_path):
    """验证技能写入指定用户的命名空间，且能被同命名空间的 StoreBackend 读到。"""
    from deepagents.backends.store import StoreBackend

    store = InMemoryStore()
    _write_demo_skill(tmp_path)

    copied = asyncio.run(sync_skills_store(tmp_path, store, "alice"))

    assert copied == 2
    keys = sorted(item.key for item in store.search(user_namespace("alice")))
    assert keys == [
        f"{SKILLS_VIRTUAL_ROOT}/demo/SKILL.md",
        f"{SKILLS_VIRTUAL_ROOT}/demo/scripts/run.py",
    ]
    assert store.search(user_namespace("bob")) == []

    backend = StoreBackend(namespace=lambda _runtime: user_namespace("alice"), store=store)
    listing = backend.ls(SKILLS_VIRTUAL_ROOT)
    assert listing.error is None
    assert [entry["path"] for entry in listing.entries or []] == [
        f"{SKILLS_VIRTUAL_ROOT}/demo/"
    ]

    content = backend.read(f"{SKILLS_VIRTUAL_ROOT}/demo/SKILL.md")
    assert content.file_data["content"] == "# demo"
    assert content.file_data["encoding"] == "utf-8"


def test_sync_skills_store_only_writes_when_skill_dirs_change(tmp_path):
    """验证技能目录集合未变化时跳过写入，增删技能目录后重新同步。"""
    store = InMemoryStore()
    _write_demo_skill(tmp_path)

    assert asyncio.run(sync_skills_store(tmp_path, store, "alice")) == 2
    assert asyncio.run(sync_skills_store(tmp_path, store, "alice")) == 0

    extra_dir = tmp_path / "extra"
    extra_dir.mkdir()
    (extra_dir / "SKILL.md").write_text("# extra", encoding="utf-8")

    assert asyncio.run(sync_skills_store(tmp_path, store, "alice")) == 3
    keys = sorted(item.key for item in store.search(user_namespace("alice")))
    assert keys == [
        f"{SKILLS_VIRTUAL_ROOT}/demo/SKILL.md",
        f"{SKILLS_VIRTUAL_ROOT}/demo/scripts/run.py",
        f"{SKILLS_VIRTUAL_ROOT}/extra/SKILL.md",
    ]

    shutil.rmtree(extra_dir)

    assert asyncio.run(sync_skills_store(tmp_path, store, "alice")) == 2
