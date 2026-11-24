import sqlite3
from contextlib import closing
from pathlib import Path

from deepclaw.web_backend.auth.store import migrate_legacy_auth_db_if_needed
from deepclaw.web_backend.db import sqlite_db_path_from_url, resolve_metadata_db_url

LEGACY_TABLES = {
    "auth.db": ("authuser", "accesstokenrecord"),
    "rbac.db": ("rbac_catalog_roles", "rbac_policy_rules", "rbac_role_rules", "rbac_policy_revision"),
    "channels.db": (
        "channel_users", "channel_sessions", "channel_message_records", "channel_runtime_states",
        "channel_bindings", "channel_jobs", "channel_leases",
    ),
    "devices.db": ("devices", "device_pairings", "device_tasks"),
    "knowledge_bases.db": ("knowledge_bases", "knowledge_base_documents", "knowledge_upload_tasks"),
    "cron.db": ("cron_jobs",),
}


def migrate_sqlite_metadata(home: Path) -> None:
    """事务性复制历史 SQLite 表及索引，保留已有字段和主键。

    Args:
        home: 旧数据库文件所在的运行目录。
    """
    target = sqlite_db_path_from_url(resolve_metadata_db_url())
    if target is None:
        return
    migrate_legacy_auth_db_if_needed(home)
    sources = [
        (path, tables)
        for filename, tables in LEGACY_TABLES.items()
        if (path := (home / filename).resolve()).is_file() and path != target
    ]
    if not sources:
        return
    with closing(sqlite3.connect(target, timeout=30, uri=True)) as connection, connection:
        for index, (path, _) in enumerate(sources):
            connection.execute(f"ATTACH DATABASE ? AS previous_{index}", (path.as_uri() + "?mode=ro",))
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            "CREATE TABLE IF NOT EXISTS metadata_imports (source TEXT PRIMARY KEY)"
        )
        for index, (path, tables) in enumerate(sources):
            existing = connection.execute(
                "SELECT 1 FROM metadata_imports WHERE source = ?", (path.name,)
            ).fetchone()
            if existing:
                continue
            for table in tables:
                copy_legacy_table(connection, f"previous_{index}", table)
            connection.execute("INSERT INTO metadata_imports(source) VALUES (?)", (path.name,))


def copy_legacy_table(connection: sqlite3.Connection, source: str, table: str) -> None:
    """复制固定清单中的旧表，并在目标冲突时中止迁移。

    Args:
        connection: 持有迁移事务的 SQLite 连接。
        source: 已挂载的历史数据库别名。
        table: 允许迁移的历史表名。
    """
    schema = connection.execute(
        f"SELECT sql FROM {source}.sqlite_master WHERE type = 'table' AND name = ?", (table,)
    ).fetchone()
    if schema is None:
        return
    target_exists = connection.execute(
        "SELECT 1 FROM main.sqlite_master WHERE type = 'table' AND name = ?", (table,)
    ).fetchone()
    if target_exists:
        source_columns = [row[1] for row in connection.execute(f'PRAGMA {source}.table_info("{table}")')]
        target_columns = {row[1] for row in connection.execute(f'PRAGMA main.table_info("{table}")')}
        if all(column in target_columns for column in source_columns):
            columns = ", ".join('"' + column.replace('"', '""') + '"' for column in source_columns)
            difference = connection.execute(
                f'SELECT {columns} FROM {source}."{table}" EXCEPT SELECT {columns} FROM main."{table}" LIMIT 1'
            ).fetchone()
            if difference is None:
                return
        raise RuntimeError(f"统一 SQLite 中已存在与旧库不一致的 {table} 表，请先核对存量数据。")
    connection.execute(schema[0])
    connection.execute(f'INSERT INTO main."{table}" SELECT * FROM {source}."{table}"')
    indexes = connection.execute(
        f"SELECT sql FROM {source}.sqlite_master WHERE type = 'index' AND tbl_name = ? AND sql IS NOT NULL",
        (table,),
    )
    for (statement,) in indexes:
        connection.execute(statement)

