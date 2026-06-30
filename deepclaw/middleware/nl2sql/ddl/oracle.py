from __future__ import annotations
import os
import platform
from urllib.parse import parse_qs, urlparse

import oracledb
from loguru import logger

from deepclaw.middleware.nl2sql.ddl.base import BaseDdlFetcher, register_ddl_fetcher

DEFAULT_SCHEMA = None  # Oracle 默认使用登录用户的 schema


def parse_oracle_url(database_url: str) -> dict:
    """将 Oracle URL 解析为 oracledb.connect 的关键字参数。"""
    scheme = database_url.split("://", 1)[0]
    for suffix in ("+oracledb", "+cx_oracle"):
        if scheme.endswith(suffix):
            database_url = database_url.replace(f"{scheme}://", f"{scheme[: -len(suffix)]}://", 1)
            break
    parsed = urlparse(database_url)
    params = parse_qs(parsed.query)
    service_name = params.get("service_name", [None])[0]
    sid = params.get("sid", [None])[0]
    host = parsed.hostname or ""
    port = parsed.port or 1521
    if service_name:
        dsn = f"{host}:{port}/{service_name}"
    elif sid:
        dsn = f"{host}:{port}/{sid}"
    else:
        dsn = f"{host}:{port}"
    result = {"user": parsed.username, "password": parsed.password, "dsn": dsn}
    return {k: v for k, v in result.items() if v is not None}


def init_oracle_thick_client() -> None:
    """按平台规则初始化 Oracle thick 模式客户端。

    Args:
        无。
    """
    lib_dir = os.environ.get("ORACLE_CLIENT_LIB_DIR")
    init_kwargs = {}
    if platform.system() == "Windows" and lib_dir:
        init_kwargs["lib_dir"] = lib_dir
    oracledb.init_oracle_client(**init_kwargs)


@register_ddl_fetcher
class OracleDdlFetcher(BaseDdlFetcher):
    """Oracle DDL 拉取器，使用 oracledb 瘦驱动模式。"""

    schemes = ("oracle",)

    @classmethod
    def normalize_url(cls, database_url: str) -> str:
        parsed_scheme = database_url.split("://", 1)[0]
        for driver_suffix in ("+oracledb", "+cx_oracle"):
            if parsed_scheme.endswith(driver_suffix):
                base_scheme = parsed_scheme[: -len(driver_suffix)]
                return database_url.replace(f"{parsed_scheme}://", f"{base_scheme}://", 1)
        return super().normalize_url(database_url)

    def _make_connection(self, database_url: str):
        """创建 oracledb 连接，thin 模式失败时自动尝试 thick 模式。"""
        kwargs = parse_oracle_url(database_url)
        try:
            return oracledb.connect(**kwargs)
        except oracledb.Error as exc:
            if "DPY-3010" not in str(exc):
                raise
            logger.info("Oracle thin 模式不支持该服务器版本，尝试 thick 模式")
            return self._make_connection_thick(**kwargs)

    @staticmethod
    def _make_connection_thick(**kwargs):
        """使用 thick 模式创建连接。"""
        try:
            init_oracle_thick_client()
        except Exception as init_exc:
            raise RuntimeError(
                "Oracle thick 模式初始化失败，请安装 Oracle Instant Client 并设置 ORACLE_CLIENT_LIB_DIR。"
                f" 参考: https://python-oracledb.readthedocs.io/en/latest/user_guide/initialization.html\n错误: {init_exc}"
            ) from init_exc
        return oracledb.connect(**kwargs)

    def fetch_ddl(
        self,
        database_url: str,
        *,
        table_names: list[str] | None = None,
        schema: str | None = None,
    ) -> str:
        database_url = self.normalize_url(database_url)
        try:
            with self._make_connection(database_url) as conn:
                owner = schema.upper() if schema else conn.username.upper()
                with conn.cursor() as cur:
                    if table_names is None:
                        table_names = self._list_tables(cur, owner)

                    if not table_names:
                        return f"-- schema `{owner}` 下未找到数据表"

                    return "\n\n".join(
                        self._build_create_table_ddl(cur, owner, table_name)
                        for table_name in table_names
                    )
        except Exception as exc:
            logger.warning(f"获取 Oracle DDL 失败: {exc}")
            return f"-- 获取数据库表结构失败: {exc}"

    def _list_tables(self, cur: oracledb.Cursor, owner: str) -> list[str]:
        cur.execute(
            """
            SELECT table_name
            FROM all_tables
            WHERE owner = :owner
            ORDER BY table_name
            """,
            owner=owner,
        )
        return [row[0] for row in cur.fetchall()]

    def _build_create_table_ddl(
        self,
        cur: oracledb.Cursor,
        owner: str,
        table_name: str,
    ) -> str:
        # 获取列信息
        cur.execute(
            """
            SELECT
                col.column_name,
                col.data_type,
                col.data_length,
                col.data_precision,
                col.data_scale,
                col.nullable,
                col.data_default,
                col.char_length,
                com.comments
            FROM all_tab_columns col
            LEFT JOIN all_col_comments com
              ON col.owner = com.owner
             AND col.table_name = com.table_name
             AND col.column_name = com.column_name
            WHERE col.owner = :owner
              AND col.table_name = :table_name
            ORDER BY col.column_id
            """,
            owner=owner,
            table_name=table_name,
        )
        columns = cur.fetchall()
        if not columns:
            return f"-- 表 {owner}.{table_name} 不存在或无列定义"

        # 获取主键列
        cur.execute(
            """
            SELECT acc.column_name
            FROM all_constraints ac
            JOIN all_cons_columns acc
              ON ac.constraint_name = acc.constraint_name
             AND ac.owner = acc.owner
            WHERE ac.owner = :owner
              AND ac.table_name = :table_name
              AND ac.constraint_type = 'P'
            ORDER BY acc.position
            """,
            owner=owner,
            table_name=table_name,
        )
        pk_columns = [row[0] for row in cur.fetchall()]

        # 构建列定义
        col_defs: list[str] = []
        column_comments: list[tuple[str, str | None]] = []
        for row in columns:
            (
                col_name,
                data_type,
                data_length,
                data_precision,
                data_scale,
                nullable,
                data_default,
                char_length,
                column_comment,
            ) = row

            # 将 Oracle 数据类型映射为 DDL 类型字符串
            col_type = self._map_oracle_type(data_type, data_length, data_precision, data_scale, char_length)

            line = f'    "{col_name}" {col_type}'
            if data_default is not None:
                line += f" DEFAULT {data_default}"
            if nullable == "N":
                line += " NOT NULL"
            col_defs.append(line)
            column_comments.append((col_name, column_comment))

        ddl = f'CREATE TABLE "{table_name}" (\n' + ",\n".join(col_defs)
        if pk_columns:
            pk_list = ", ".join(f'"{col}"' for col in pk_columns)
            ddl += f",\n    PRIMARY KEY ({pk_list})"
        ddl += "\n);"
        comment_ddls = self.build_column_comment_ddls(table_name, column_comments)
        if comment_ddls:
            ddl += f"\n\n{comment_ddls}"
        return ddl

    @staticmethod
    def _map_oracle_type(
        data_type: str,
        data_length: int | None,
        data_precision: int | None,
        data_scale: int | None,
        char_length: int | None,
    ) -> str:
        """将 Oracle 数据类型映射为 DDL 类型字符串。"""
        dt = data_type.upper()

        if dt == "VARCHAR2":
            return f"VARCHAR2({char_length or data_length or 255})"
        if dt == "NVARCHAR2":
            return f"NVARCHAR2({char_length or data_length or 255})"
        if dt == "CHAR":
            return f"CHAR({char_length or data_length or 1})"
        if dt == "NCHAR":
            return f"NCHAR({char_length or data_length or 1})"
        if dt == "NUMBER":
            if data_precision is not None and data_scale is not None and data_scale > 0:
                return f"NUMBER({data_precision},{data_scale})"
            if data_precision is not None:
                return f"NUMBER({data_precision})"
            return "NUMBER"
        if dt == "FLOAT":
            return f"FLOAT({data_precision})" if data_precision else "FLOAT"
        if dt == "BINARY_FLOAT":
            return "BINARY_FLOAT"
        if dt == "BINARY_DOUBLE":
            return "BINARY_DOUBLE"
        if dt in ("DATE",):
            return "DATE"
        if dt.startswith("TIMESTAMP"):
            return dt
        if dt in ("CLOB", "NCLOB"):
            return dt
        if dt == "BLOB":
            return "BLOB"
        if dt == "RAW":
            return f"RAW({data_length or 2000})"
        if dt in ("VARCHAR", "VARCHAR2"):
            return f"VARCHAR({data_length or 255})"

        # 兜底：保持原始类型
        return dt
