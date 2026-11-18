import pathlib
from pathlib import Path

from deepclaw import constant


def _make_checkout(root: Path) -> Path:
    """构造一个带源码检出标记的最小目录。

    Args:
        root: 目标根目录。

    Returns:
        同一个根目录，便于链式调用。
    """

    (root / "deepclaw").mkdir(parents=True, exist_ok=True)
    (root / "pyproject.toml").write_text("", encoding="utf-8")
    return root


def test_resolve_home_path_prefers_env_override(monkeypatch, tmp_path: Path):
    """验证 DEEPCLAW_HOME 优先于检出目录与用户主目录。"""

    monkeypatch.setenv("DEEPCLAW_HOME", str(tmp_path / "custom-home"))
    monkeypatch.setattr(constant, "ROOT_DIR", _make_checkout(tmp_path))

    assert constant.resolve_home_path() == (tmp_path / "custom-home").resolve()


def test_resolve_home_path_keeps_checkout_layout(monkeypatch, tmp_path: Path):
    """验证源码检出仍使用仓库内的 .deepclaw，避免既有数据迁移。"""

    monkeypatch.delenv("DEEPCLAW_HOME", raising=False)
    monkeypatch.setattr(constant, "ROOT_DIR", _make_checkout(tmp_path))

    assert constant.resolve_home_path() == tmp_path / ".deepclaw"


def test_resolve_home_path_falls_back_to_user_home(monkeypatch, tmp_path: Path):
    """验证安装在 site-packages 等只读位置时回退到用户主目录。"""

    monkeypatch.delenv("DEEPCLAW_HOME", raising=False)
    installed_root = tmp_path / "site-packages"
    installed_root.mkdir()
    monkeypatch.setattr(constant, "ROOT_DIR", installed_root)
    monkeypatch.setattr(pathlib.Path, "home", classmethod(lambda cls: tmp_path / "user"))

    assert constant.resolve_home_path() == tmp_path / "user" / ".deepclaw"


def test_resolve_frontend_path_prefers_source_checkout(monkeypatch, tmp_path: Path):
    """验证源码检出优先使用仓库下的 frontend/out。"""

    frontend_out = tmp_path / "frontend" / "out"
    frontend_out.mkdir(parents=True)
    bundled = tmp_path / "bundled"
    bundled.mkdir()
    monkeypatch.setattr(constant, "ROOT_DIR", tmp_path)
    monkeypatch.setattr(constant, "BUNDLED_FRONTEND_PATH", bundled)

    assert constant.resolve_frontend_path() == frontend_out


def test_resolve_frontend_path_falls_back_to_bundled_copy(monkeypatch, tmp_path: Path):
    """验证 wheel 安装时使用包内打包的前端副本。"""

    bundled = tmp_path / "bundled"
    bundled.mkdir()
    monkeypatch.setattr(constant, "ROOT_DIR", tmp_path)
    monkeypatch.setattr(constant, "BUNDLED_FRONTEND_PATH", bundled)

    assert constant.resolve_frontend_path() == bundled


def test_resolve_frontend_path_returns_none_without_assets(monkeypatch, tmp_path: Path):
    """验证前端资源缺失时返回 None，由调用方跳过静态托管。"""

    monkeypatch.setattr(constant, "ROOT_DIR", tmp_path)
    monkeypatch.setattr(constant, "BUNDLED_FRONTEND_PATH", tmp_path / "missing")

    assert constant.resolve_frontend_path() is None
