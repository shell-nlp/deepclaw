from __future__ import annotations

from abc import ABC, abstractmethod
from urllib.parse import urlparse, urlunparse


class BaseDdlFetcher(ABC):
    """数据库 DDL 拉取器基类，新增数据库类型时继承并实现 fetch_ddl。"""

    # 该 fetcher 支持的 URL scheme（不含 driver 后缀，如 postgresql+psycopg）
    schemes: tuple[str, ...] = ()

    @classmethod
    def matches_scheme(cls, scheme: str) -> bool:
        base_scheme = scheme.split("+", 1)[0]
        return base_scheme in cls.schemes

    @classmethod
    def normalize_url(cls, database_url: str) -> str:
        """将 SQLAlchemy 风格连接串转为驱动原生格式，子类可覆盖。"""
        parsed = urlparse(database_url)
        base_scheme = parsed.scheme.split("+", 1)[0]
        if "+" in parsed.scheme:
            parsed = parsed._replace(scheme=base_scheme)
            return urlunparse(parsed)
        return database_url

    @abstractmethod
    def fetch_ddl(
        self,
        database_url: str,
        *,
        table_names: list[str] | None = None,
        schema: str | None = None,
    ) -> str:
        """拉取指定表（或全部表）的 DDL 文本。"""

    @staticmethod
    def _escape_comment_literal(comment: str) -> str:
        """转义 SQL 注释字面量中的单引号。

        Args:
            comment: 原始注释文本。
        """
        return comment.replace("'", "''")

    @classmethod
    def build_column_comment_ddls(
        cls,
        table_name: str,
        column_comments: list[tuple[str, str | None]],
    ) -> str:
        """构建字段注释 DDL 语句。

        Args:
            table_name: 表名。
            column_comments: 字段名与字段注释的映射列表。
        """
        ddl_lines: list[str] = []
        for column_name, comment in column_comments:
            if not comment:
                continue
            escaped_comment = cls._escape_comment_literal(comment)
            ddl_lines.append(
                f'COMMENT ON COLUMN "{table_name}"."{column_name}" IS '
                f"'{escaped_comment}';"
            )
        return "\n".join(ddl_lines)


_DDL_FETCHER_REGISTRY: dict[str, type[BaseDdlFetcher]] = {}


def register_ddl_fetcher(fetcher_cls: type[BaseDdlFetcher]) -> type[BaseDdlFetcher]:
    """注册 DDL fetcher，同一 scheme 后注册者覆盖前者。"""
    for scheme in fetcher_cls.schemes:
        _DDL_FETCHER_REGISTRY[scheme] = fetcher_cls
    return fetcher_cls


def resolve_database_scheme(database_url: str) -> str:
    """从连接串解析基础 scheme（postgresql / mysql / sqlite 等）。"""
    parsed = urlparse(database_url)
    if not parsed.scheme:
        raise ValueError(f"无效的数据库连接串: {database_url}")
    return parsed.scheme.split("+", 1)[0]


def get_ddl_fetcher(database_url: str) -> BaseDdlFetcher:
    """根据连接串选择对应的 DDL fetcher 实例。"""
    scheme = resolve_database_scheme(database_url)
    fetcher_cls = _DDL_FETCHER_REGISTRY.get(scheme)
    if fetcher_cls is None:
        supported = ", ".join(sorted(_DDL_FETCHER_REGISTRY))
        raise ValueError(
            f"暂不支持的数据库类型: {scheme}，当前已注册: {supported or '无'}"
        )
    return fetcher_cls()
