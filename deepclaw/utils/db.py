"""异步数据库连接工具。"""

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession


def make_async_url(db_url: str) -> str:
    """把同步数据库 URL 转换为异步驱动 URL。

    Args:
        db_url: 原始数据库 URL。

    Returns:
        适配 aiosqlite 或 asyncpg 的异步 URL。
    """
    if db_url.startswith("sqlite"):
        return "sqlite+aiosqlite:" + db_url[len("sqlite:"):]
    if db_url.startswith("postgresql"):
        return "postgresql+asyncpg:" + db_url[len("postgresql:"):]
    return db_url


def create_async_engine_from_url(db_url: str, echo: bool = False):
    """按数据库类型创建异步 SQLAlchemy 引擎。

    Args:
        db_url: 原始数据库 URL。
        echo: 是否输出 SQL 日志。

    Returns:
        已配置连接参数的异步引擎。
    """
    async_db_url = make_async_url(db_url)
    connect_args = {"check_same_thread": False} if db_url.startswith("sqlite") else {}
    engine_kwargs = {"echo": echo, "connect_args": connect_args}
    if db_url.startswith("postgresql"):
        engine_kwargs.update(pool_pre_ping=True, pool_recycle=1800)
    engine = create_async_engine(async_db_url, **engine_kwargs)
    return engine


def build_async_sessionmaker(engine):
    """基于异步引擎创建 SQLModel 会话工厂。

    Args:
        engine: SQLAlchemy 异步引擎。

    Returns:
        使用 AsyncSession 的会话工厂。
    """
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
