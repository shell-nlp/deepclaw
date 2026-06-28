from deepclaw.middleware.nl2sql.ddl.base import (
    BaseDdlFetcher,
    get_ddl_fetcher,
    register_ddl_fetcher,
    resolve_database_scheme,
)
try:
    from . import oracle as _oracle  # noqa: F401 — 触发 Oracle 注册
except ImportError:
    pass  # oracledb 未安装，跳过 Oracle DDL 支持
from . import pgsql as _pgsql  # noqa: F401 — 触发 PostgreSQL 注册

__all__ = [
    "BaseDdlFetcher",
    "fetch_schema_ddl",
    "get_ddl_fetcher",
    "register_ddl_fetcher",
    "resolve_database_scheme",
]


def fetch_schema_ddl(
    database_url: str,
    *,
    table_names: list[str] | None = None,
    schema: str | None = None,
) -> str:
    """按连接串自动选择 fetcher 并拉取 DDL。"""
    try:
        fetcher = get_ddl_fetcher(database_url)
    except ValueError as exc:
        return f"-- {exc}"
    return fetcher.fetch_ddl(database_url, table_names=table_names, schema=schema)
