import os
from pathlib import Path

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession

from deepclaw.constant import home_path
from deepclaw.settings import settings


def make_async_url(db_url: str) -> str:
    if db_url.startswith("sqlite"):
        return "sqlite+aiosqlite:" + db_url[len("sqlite:"):]
    if db_url.startswith("postgresql"):
        return "postgresql+asyncpg:" + db_url[len("postgresql:"):]
    return db_url


def build_home_sqlite_db_url(filename: str) -> str:
    os.makedirs(home_path, exist_ok=True)
    return f"sqlite:///{os.path.join(home_path, filename)}"


def resolve_metadata_db_url(filename: str) -> str:
    if settings.PG_DATABASE_URL:
        return settings.PG_DATABASE_URL
    return build_home_sqlite_db_url(filename)


def sqlite_db_path_from_url(db_url: str) -> Path | None:
    if not db_url.startswith("sqlite:///"):
        return None
    return Path(db_url[len("sqlite:///") :]).resolve()


def should_import_home_sqlite(*, filename: str, target_db_url: str) -> Path | None:
    source_path = Path(home_path).joinpath(filename).resolve()
    if not source_path.exists():
        return None
    target_path = sqlite_db_path_from_url(target_db_url)
    if target_path is not None and target_path == source_path:
        return None
    return source_path


def create_async_engine_from_url(db_url: str, echo: bool = False):
    async_db_url = make_async_url(db_url)
    connect_args = {"check_same_thread": False} if db_url.startswith("sqlite") else {}
    engine_kwargs = {"echo": echo, "connect_args": connect_args}
    if db_url.startswith("postgresql"):
        engine_kwargs.update(pool_pre_ping=True, pool_recycle=1800)
    engine = create_async_engine(async_db_url, **engine_kwargs)
    return engine


def build_async_sessionmaker(engine):
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
