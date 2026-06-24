from __future__ import annotations

import psycopg
from loguru import logger

from deepclaw.middleware.nl2sql.ddl.base import BaseDdlFetcher, register_ddl_fetcher

DEFAULT_SCHEMA = "public"


@register_ddl_fetcher
class PgDdlFetcher(BaseDdlFetcher):
    """PostgreSQL DDL 拉取器。"""

    schemes = ("postgresql", "postgres")

    @classmethod
    def normalize_url(cls, database_url: str) -> str:
        parsed_scheme = database_url.split("://", 1)[0]
        for driver_suffix in ("+psycopg", "+asyncpg"):
            if parsed_scheme.endswith(driver_suffix):
                base_scheme = parsed_scheme[: -len(driver_suffix)]
                return database_url.replace(f"{parsed_scheme}://", f"{base_scheme}://", 1)
        return super().normalize_url(database_url)

    def fetch_ddl(
        self,
        database_url: str,
        *,
        table_names: list[str] | None = None,
        schema: str | None = None,
    ) -> str:
        schema_name = schema or DEFAULT_SCHEMA
        database_url = self.normalize_url(database_url)
        try:
            with psycopg.connect(database_url) as conn:
                with conn.cursor() as cur:
                    if table_names is None:
                        table_names = self._list_tables(cur, schema_name)

                    if not table_names:
                        return f"-- schema `{schema_name}` 下未找到数据表"

                    return "\n\n".join(
                        self._build_create_table_ddl(cur, schema_name, table_name)
                        for table_name in table_names
                    )
        except Exception as exc:
            logger.warning(f"获取 PostgreSQL DDL 失败: {exc}")
            return f"-- 获取数据库表结构失败: {exc}"

    def _list_tables(self, cur: psycopg.Cursor, schema: str) -> list[str]:
        cur.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = %s
              AND table_type = 'BASE TABLE'
            ORDER BY table_name
            """,
            (schema,),
        )
        return [row[0] for row in cur.fetchall()]

    def _build_create_table_ddl(
        self,
        cur: psycopg.Cursor,
        schema: str,
        table_name: str,
    ) -> str:
        cur.execute(
            """
            SELECT
                a.attname,
                pg_catalog.format_type(a.atttypid, a.atttypmod),
                NOT a.attnotnull,
                pg_get_expr(ad.adbin, ad.adrelid)
            FROM pg_catalog.pg_attribute a
            JOIN pg_catalog.pg_class c ON a.attrelid = c.oid
            JOIN pg_catalog.pg_namespace n ON c.relnamespace = n.oid
            LEFT JOIN pg_catalog.pg_attrdef ad
                ON a.attrelid = ad.adrelid AND a.attnum = ad.adnum
            WHERE n.nspname = %s
              AND c.relname = %s
              AND a.attnum > 0
              AND NOT a.attisdropped
            ORDER BY a.attnum
            """,
            (schema, table_name),
        )
        columns = cur.fetchall()
        if not columns:
            return f"-- 表 {schema}.{table_name} 不存在或无列定义"

        cur.execute(
            """
            SELECT kcu.column_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
              ON tc.constraint_name = kcu.constraint_name
             AND tc.table_schema = kcu.table_schema
            WHERE tc.constraint_type = 'PRIMARY KEY'
              AND tc.table_schema = %s
              AND tc.table_name = %s
            ORDER BY kcu.ordinal_position
            """,
            (schema, table_name),
        )
        pk_columns = [row[0] for row in cur.fetchall()]

        col_defs: list[str] = []
        for col_name, col_type, is_nullable, col_default in columns:
            line = f'    "{col_name}" {col_type}'
            if not is_nullable:
                line += " NOT NULL"
            if col_default is not None:
                line += f" DEFAULT {col_default}"
            col_defs.append(line)

        ddl = f'CREATE TABLE "{table_name}" (\n' + ",\n".join(col_defs)
        if pk_columns:
            pk_list = ", ".join(f'"{column}"' for column in pk_columns)
            ddl += f",\n    PRIMARY KEY ({pk_list})"
        ddl += "\n);"
        return ddl
