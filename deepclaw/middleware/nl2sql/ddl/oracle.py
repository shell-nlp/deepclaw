from __future__ import annotations

from contextlib import contextmanager
import os
import platform
import threading
import time
from collections.abc import Iterator
from urllib.parse import parse_qs, urlparse

try:
    import oracledb
except ModuleNotFoundError:  # pragma: no cover - Oracle 驱动为可选依赖
    oracledb = None  # type: ignore[assignment]

from loguru import logger

from deepclaw.middleware.nl2sql.ddl.base import BaseDdlFetcher, register_ddl_fetcher

DEFAULT_SCHEMA = None  # Oracle 默认使用登录用户的 schema


def _positive_env_int(name: str, default: int) -> int:
    """读取正整数环境变量，非法值时回退默认值。

    Args:
        name: 环境变量名称。
        default: 环境变量缺失或非法时使用的默认值。
    """
    try:
        return max(1, int(os.getenv(name, str(default))))
    except (TypeError, ValueError):
        return default


def _non_negative_env_int(name: str, default: int) -> int:
    """读取非负整数环境变量，非法值时回退默认值。

    Args:
        name: 环境变量名称。
        default: 环境变量缺失或非法时使用的默认值。
    """
    try:
        return max(0, int(os.getenv(name, str(default))))
    except (TypeError, ValueError):
        return default


def _env_bool(name: str, default: bool) -> bool:
    """读取布尔环境变量，非法值时回退默认值。

    Args:
        name: 环境变量名称。
        default: 环境变量缺失或非法时使用的默认值。
    """
    value = os.getenv(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


ORACLE_POOL_MAX = _positive_env_int("NL2SQL_ORACLE_POOL_MAX", 4)
ORACLE_POOL_WAIT_SECONDS = _positive_env_int("NL2SQL_ORACLE_POOL_WAIT_SECONDS", 5)
ORACLE_DDL_CACHE_TTL_SECONDS = _non_negative_env_int("NL2SQL_ORACLE_DDL_CACHE_TTL_SECONDS", 300)
ORACLE_CIRCUIT_COOLDOWN_SECONDS = _positive_env_int("NL2SQL_ORACLE_CIRCUIT_COOLDOWN_SECONDS", 30)
ORACLE_QUERY_TIMEOUT_SECONDS = _non_negative_env_int("NL2SQL_ORACLE_QUERY_TIMEOUT_SECONDS", 120)
ORACLE_THICK_MODE = _env_bool("NL2SQL_ORACLE_THICK_MODE", False)

_ORACLE_POOL_LOCK = threading.RLock()
_ORACLE_POOL_SEMAPHORE = threading.BoundedSemaphore(ORACLE_POOL_MAX)
_ORACLE_POOLS: dict[str, oracledb.ConnectionPool] = {}
_ORACLE_CIRCUITS: dict[str, tuple[int, float]] = {}
_ORACLE_DDL_CACHE: dict[tuple[str, str | None, tuple[str, ...]], tuple[float, str]] = {}
_ORACLE_TABLE_CACHE: dict[tuple[str, str | None], tuple[float, list[str]]] = {}
_ORACLE_THICK_INIT_LOCK = threading.Lock()
_ORACLE_THICK_INITIALIZED = False


def _purge_expired_cache_locked(now: float) -> None:
    """清理已超过 TTL 的 Oracle 元数据缓存。

    Args:
        now: 当前单调时钟时间戳。
    """
    if ORACLE_DDL_CACHE_TTL_SECONDS <= 0:
        _ORACLE_DDL_CACHE.clear()
        _ORACLE_TABLE_CACHE.clear()
        return
    deadline = now - ORACLE_DDL_CACHE_TTL_SECONDS
    for key, (created_at, _) in list(_ORACLE_DDL_CACHE.items()):
        if created_at <= deadline:
            _ORACLE_DDL_CACHE.pop(key, None)
    for key, (created_at, _) in list(_ORACLE_TABLE_CACHE.items()):
        if created_at <= deadline:
            _ORACLE_TABLE_CACHE.pop(key, None)


def clear_oracle_ddl_cache(
    database_url: str | None = None,
    *,
    schema: str | None = None,
) -> None:
    """清理 Oracle DDL 和表名元数据缓存。

    Args:
        database_url: 只清理指定数据库连接的缓存；为 None 时清理全部缓存。
        schema: 只清理指定 schema 的缓存；为 None 时匹配所有 schema。
    """
    normalized_url = OracleDdlFetcher.normalize_url(database_url) if database_url else None
    normalized_schema = schema.upper() if schema else None
    with _ORACLE_POOL_LOCK:
        for key in list(_ORACLE_DDL_CACHE):
            url, cached_schema, _ = key
            if (normalized_url is None or url == normalized_url) and (
                normalized_schema is None or cached_schema == normalized_schema
            ):
                _ORACLE_DDL_CACHE.pop(key, None)
        for key in list(_ORACLE_TABLE_CACHE):
            url, cached_schema = key
            if (normalized_url is None or url == normalized_url) and (
                normalized_schema is None or cached_schema == normalized_schema
            ):
                _ORACLE_TABLE_CACHE.pop(key, None)


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


def _is_listener_refused(exc: Exception) -> bool:
    """判断异常是否表示 Oracle listener 无法分配服务端连接。

    Args:
        exc: Oracle 驱动抛出的连接异常。
    """
    message = str(exc).upper()
    return any(marker in message for marker in ("DPY-6000", "DPY-6005", "ORA-12518"))


def _is_thin_mode_unsupported(exc: Exception) -> bool:
    """判断异常是否表示 Thin 模式不支持目标 Oracle 版本。

    Args:
        exc: Oracle 驱动抛出的连接异常。
    """
    return "DPY-3010" in str(exc).upper()


def _record_listener_failure(pool_key: str) -> None:
    """记录 listener 拒绝连接并延长当前连接池的熔断窗口。

    Args:
        pool_key: 连接池缓存键。
    """
    with _ORACLE_POOL_LOCK:
        failures, _ = _ORACLE_CIRCUITS.get(pool_key, (0, 0.0))
        cooldown = min(ORACLE_CIRCUIT_COOLDOWN_SECONDS, 2 ** min(failures, 5))
        _ORACLE_CIRCUITS[pool_key] = (failures + 1, time.monotonic() + cooldown)


def _configure_oracle_connection(conn: oracledb.Connection) -> None:
    """为池中连接设置单次数据库调用超时。

    Args:
        conn: 已从 Oracle 连接池获取的连接。
    """
    if ORACLE_QUERY_TIMEOUT_SECONDS > 0:
        conn.call_timeout = ORACLE_QUERY_TIMEOUT_SECONDS * 1000


def _create_oracle_pool(pool_key: str, kwargs: dict[str, str]) -> oracledb.ConnectionPool:
    """创建受限的 Oracle 连接池，必要时初始化 thick 模式。

    Args:
        pool_key: 连接池缓存键，仅用于异常信息和日志。
        kwargs: Oracle 连接参数。
    """
    global _ORACLE_THICK_INITIALIZED

    pool_kwargs = {
        **kwargs,
        "min": 0,
        "max": ORACLE_POOL_MAX,
        "increment": 1,
        "getmode": oracledb.POOL_GETMODE_TIMEDWAIT,
        "wait_timeout": ORACLE_POOL_WAIT_SECONDS * 1000,
        "timeout": 300,
        "max_lifetime_session": 1800,
        "ping_interval": 60,
    }
    try:
        return oracledb.create_pool(**pool_kwargs)
    except oracledb.Error as exc:
        if "DPY-3010" not in str(exc):
            raise
        logger.info(f"Oracle thin 模式不支持该服务器版本，连接池切换 thick 模式: {pool_key}")
        with _ORACLE_THICK_INIT_LOCK:
            if not _ORACLE_THICK_INITIALIZED:
                init_oracle_thick_client()
                _ORACLE_THICK_INITIALIZED = True
        return oracledb.create_pool(**pool_kwargs)


def _get_oracle_pool(database_url: str) -> tuple[str, oracledb.ConnectionPool]:
    """获取或创建按连接参数复用的 Oracle 连接池。

    Args:
        database_url: Oracle 数据库连接串。
    """
    _ensure_oracle_thick_mode()
    kwargs = parse_oracle_url(database_url)
    pool_key = repr(tuple(sorted(kwargs.items())))
    with _ORACLE_POOL_LOCK:
        pool = _ORACLE_POOLS.get(pool_key)
        if pool is None:
            pool = _create_oracle_pool(pool_key, kwargs)
            _ORACLE_POOLS[pool_key] = pool
    return pool_key, pool


@contextmanager
def get_oracle_connection(database_url: str) -> Iterator[oracledb.Connection]:
    """在全局并发上限内获取 Oracle 连接，并在退出时归还连接池。

    Args:
        database_url: Oracle 数据库连接串。

    Raises:
        RuntimeError: 连接并发已满、熔断窗口未结束或连接获取失败。
    """
    kwargs = parse_oracle_url(database_url)
    pool_key = repr(tuple(sorted(kwargs.items())))
    now = time.monotonic()
    with _ORACLE_POOL_LOCK:
        failures, retry_after = _ORACLE_CIRCUITS.get(pool_key, (0, 0.0))
        if retry_after > now:
            remaining = max(1, int(retry_after - now))
            raise RuntimeError(f"Oracle 连接暂时熔断，{remaining} 秒后重试")

    try:
        _, pool = _get_oracle_pool(database_url)
    except Exception as exc:
        if _is_listener_refused(exc):
            _record_listener_failure(pool_key)
        raise

    acquired = _ORACLE_POOL_SEMAPHORE.acquire(timeout=ORACLE_POOL_WAIT_SECONDS)
    if not acquired:
        raise RuntimeError("Oracle 连接并发已达上限，请稍后重试")

    conn = None
    try:
        try:
            conn = pool.acquire()
        except Exception as exc:
            if _is_thin_mode_unsupported(exc):
                raise RuntimeError(
                    "目标 Oracle 版本不支持 Thin 模式；请设置 NL2SQL_ORACLE_THICK_MODE=true 后重启服务"
                ) from exc
            else:
                if _is_listener_refused(exc):
                    _record_listener_failure(pool_key)
                if "DPY-4005" in str(exc).upper():
                    raise RuntimeError(
                        "Oracle 连接池已满，等待连接超时；请稍后重试或检查慢查询/锁等待"
                    ) from exc
                raise
        _configure_oracle_connection(conn)
        with _ORACLE_POOL_LOCK:
            _ORACLE_CIRCUITS.pop(pool_key, None)
        yield conn
    finally:
        try:
            if conn is not None:
                conn.close()
        finally:
            _ORACLE_POOL_SEMAPHORE.release()


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


def _ensure_oracle_thick_mode() -> None:
    """在创建 Oracle 连接池前按配置初始化 Thick 模式。

    Args:
        无。
    """
    global _ORACLE_THICK_INITIALIZED

    if not ORACLE_THICK_MODE:
        return
    with _ORACLE_THICK_INIT_LOCK:
        if not _ORACLE_THICK_INITIALIZED:
            init_oracle_thick_client()
            _ORACLE_THICK_INITIALIZED = True


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
        """获取受并发限制的 Oracle 连接池上下文。"""
        return get_oracle_connection(database_url)

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
        requested_names = tuple(name.strip().upper() for name in table_names) if table_names is not None else None
        normalized_schema = schema.upper() if schema else None
        if ORACLE_DDL_CACHE_TTL_SECONDS > 0:
            with _ORACLE_POOL_LOCK:
                _purge_expired_cache_locked(time.monotonic())
                if requested_names is None:
                    cached_tables = _ORACLE_TABLE_CACHE.get((database_url, normalized_schema))
                    cache_key = (
                        (database_url, normalized_schema, tuple(cached_tables[1]))
                        if cached_tables is not None
                        else None
                    )
                else:
                    cache_key = (database_url, normalized_schema, requested_names)
                cached = _ORACLE_DDL_CACHE.get(cache_key) if cache_key is not None else None
                if cached is not None:
                    return cached[1]
        try:
            with self._make_connection(database_url) as conn:
                owner = schema.upper() if schema else conn.username.upper()
                with conn.cursor() as cur:
                    if table_names is None:
                        table_cache_key = (database_url, normalized_schema)
                        with _ORACLE_POOL_LOCK:
                            _purge_expired_cache_locked(time.monotonic())
                            cached_tables = _ORACLE_TABLE_CACHE.get(table_cache_key)
                        if cached_tables is not None:
                            table_names = list(cached_tables[1])
                        else:
                            table_names = self._list_tables(cur, owner)
                            if ORACLE_DDL_CACHE_TTL_SECONDS > 0:
                                with _ORACLE_POOL_LOCK:
                                    _ORACLE_TABLE_CACHE[table_cache_key] = (time.monotonic(), list(table_names))

                    if not table_names:
                        return f"-- schema `{owner}` 下未找到数据表"

                    ddl = self.join_table_ddls(
                        [
                            self._build_create_table_ddl(cur, owner, table_name)
                            for table_name in table_names
                        ]
                    )
                    if ORACLE_DDL_CACHE_TTL_SECONDS > 0:
                        cache_key = (database_url, normalized_schema, tuple(name.strip().upper() for name in table_names))
                        with _ORACLE_POOL_LOCK:
                            _ORACLE_DDL_CACHE[cache_key] = (time.monotonic(), ddl)
                    return ddl
        except Exception as exc:
            logger.warning(f"获取 Oracle DDL 失败: {exc}")
            return f"-- 获取数据库表结构失败: {exc}"

    def list_tables(
        self,
        database_url: str,
        *,
        schema: str | None = None,
    ) -> list[str]:
        """返回 Oracle 数据库中所有表名列表。

        Args:
            database_url: 数据库连接串。
            schema: 显式指定的 schema 名称。
        """
        database_url = self.normalize_url(database_url)
        cache_key = (database_url, schema.upper() if schema else None)
        if ORACLE_DDL_CACHE_TTL_SECONDS > 0:
            with _ORACLE_POOL_LOCK:
                _purge_expired_cache_locked(time.monotonic())
                cached = _ORACLE_TABLE_CACHE.get(cache_key)
                if cached is not None:
                    return list(cached[1])
        with self._make_connection(database_url) as conn:
            owner = schema.upper() if schema else conn.username.upper()
            with conn.cursor() as cur:
                tables = self._list_tables(cur, owner)
        if ORACLE_DDL_CACHE_TTL_SECONDS > 0:
            with _ORACLE_POOL_LOCK:
                _ORACLE_TABLE_CACHE[cache_key] = (time.monotonic(), list(tables))
        return tables

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

        # 获取外键及其引用列，按约束名和字段位置排序以支持复合外键。
        cur.execute(
            """
            SELECT
                child.constraint_name,
                child_columns.column_name,
                parent.owner,
                parent.table_name,
                parent_columns.column_name,
                child.delete_rule
            FROM all_constraints child
            JOIN all_cons_columns child_columns
              ON child.constraint_name = child_columns.constraint_name
             AND child.owner = child_columns.owner
            JOIN all_constraints parent
              ON child.r_constraint_name = parent.constraint_name
             AND child.r_owner = parent.owner
            JOIN all_cons_columns parent_columns
              ON parent.constraint_name = parent_columns.constraint_name
             AND parent.owner = parent_columns.owner
             AND parent_columns.position = child_columns.position
            WHERE child.owner = :owner
              AND child.table_name = :table_name
              AND child.constraint_type = 'R'
            ORDER BY child.constraint_name, child_columns.position
            """,
            owner=owner,
            table_name=table_name,
        )
        foreign_key_rows = cur.fetchall()

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
        foreign_keys: dict[str, dict[str, object]] = {}
        for (
            constraint_name,
            column_name,
            referenced_owner,
            referenced_table,
            referenced_column,
            delete_rule,
        ) in foreign_key_rows:
            foreign_key = foreign_keys.setdefault(
                constraint_name,
                {
                    "columns": [],
                    "referenced_owner": referenced_owner,
                    "referenced_table": referenced_table,
                    "referenced_columns": [],
                    "delete_rule": delete_rule,
                },
            )
            foreign_key["columns"].append(column_name)
            foreign_key["referenced_columns"].append(referenced_column)
        for constraint_name, foreign_key in foreign_keys.items():
            column_list = ", ".join(f'"{column}"' for column in foreign_key["columns"])
            referenced_column_list = ", ".join(
                f'"{column}"' for column in foreign_key["referenced_columns"]
            )
            ddl += (
                f',\n    CONSTRAINT "{constraint_name}" FOREIGN KEY ({column_list}) '
                f'REFERENCES "{foreign_key["referenced_owner"]}".'
                f'"{foreign_key["referenced_table"]}" ({referenced_column_list})'
            )
            if foreign_key["delete_rule"] in {"CASCADE", "SET NULL"}:
                ddl += f' ON DELETE {foreign_key["delete_rule"]}'
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
