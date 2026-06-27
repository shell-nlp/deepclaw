from __future__ import annotations

import oracledb
from loguru import logger

from deepclaw.middleware.nl2sql.ddl.base import BaseDdlFetcher, register_ddl_fetcher

DEFAULT_SCHEMA = None  # Oracle 默认使用登录用户的 schema


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
        """创建 oracledb 连接，自动选择瘦驱动模式。"""
        return oracledb.connect(dsn=database_url)

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
                column_name,
                data_type,
                data_length,
                data_precision,
                data_scale,
                nullable,
                data_default,
                char_length
            FROM all_tab_columns
            WHERE owner = :owner
              AND table_name = :table_name
            ORDER BY column_id
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
        for row in columns:
            col_name, data_type, data_length, data_precision, data_scale, nullable, data_default, char_length = row

            # 将 Oracle 数据类型映射为 DDL 类型字符串
            col_type = self._map_oracle_type(data_type, data_length, data_precision, data_scale, char_length)

            line = f'    "{col_name}" {col_type}'
            if data_default is not None:
                line += f" DEFAULT {data_default}"
            if nullable == "N":
                line += " NOT NULL"
            col_defs.append(line)

        ddl = f'CREATE TABLE "{table_name}" (\n' + ",\n".join(col_defs)
        if pk_columns:
            pk_list = ", ".join(f'"{col}"' for col in pk_columns)
            ddl += f",\n    PRIMARY KEY ({pk_list})"
        ddl += "\n);"
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
