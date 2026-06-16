from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession


def make_async_url(db_url: str) -> str:
    if db_url.startswith("sqlite"):
        return "sqlite+aiosqlite:" + db_url[len("sqlite:"):]
    if db_url.startswith("postgresql"):
        return "postgresql+asyncpg:" + db_url[len("postgresql:"):]
    return db_url


def create_async_engine_from_url(db_url: str, echo: bool = False):
    async_db_url = make_async_url(db_url)
    connect_args = {"check_same_thread": False} if db_url.startswith("sqlite") else {}
    engine = create_async_engine(async_db_url, echo=echo, connect_args=connect_args)
    return engine


def build_async_sessionmaker(engine):
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
