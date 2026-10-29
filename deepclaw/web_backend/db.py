import os
from pathlib import Path

from deepclaw.constant import HOME_PATH
from deepclaw.settings import settings


def build_home_sqlite_db_url(filename: str) -> str:
    os.makedirs(HOME_PATH, exist_ok=True)
    return f"sqlite:///{os.path.join(HOME_PATH, filename)}"


def resolve_metadata_db_url(filename: str) -> str:
    if settings.PG_DATABASE_URL:
        return settings.PG_DATABASE_URL
    return build_home_sqlite_db_url(filename)


def sqlite_db_path_from_url(db_url: str) -> Path | None:
    if not db_url.startswith("sqlite:///"):
        return None
    return Path(db_url[len("sqlite:///") :]).resolve()


def should_import_home_sqlite(*, filename: str, target_db_url: str) -> Path | None:
    source_path = Path(HOME_PATH).joinpath(filename).resolve()
    if not source_path.exists():
        return None
    target_path = sqlite_db_path_from_url(target_db_url)
    if target_path is not None and target_path == source_path:
        return None
    return source_path


