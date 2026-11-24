from pathlib import Path

from deepclaw.constant import HOME_PATH
from deepclaw.settings import settings


def resolve_metadata_db_url() -> str:
    """解析统一业务元数据数据库地址。

    Args:
        无。
    """
    if settings.PG_DATABASE_URL:
        return settings.PG_DATABASE_URL
    configured_path = Path(settings.SQLITE_DB_PATH or "deepclaw.db").expanduser()
    path = (Path(HOME_PATH) / configured_path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{path.as_posix()}"


def sqlite_db_path_from_url(db_url: str) -> Path | None:
    if not db_url.startswith("sqlite:///"):
        return None
    return Path(db_url[len("sqlite:///") :]).resolve()


def should_import_home_sqlite(*, filename: str, target_db_url: str) -> Path | None:
    source_path = Path(HOME_PATH).joinpath(filename).resolve()
    if not source_path.exists():
        return None
    target_path = sqlite_db_path_from_url(target_db_url)
    if target_path is not None:
        return None
    return source_path


