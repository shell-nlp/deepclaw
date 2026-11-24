import shutil
import sqlite3
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import inspect, text
from sqlmodel import select

from deepclaw.web_backend.common.errors import BusinessRuleError
from deepclaw.constant import HOME_PATH
from deepclaw.web_backend.auth.models import (
    AccessTokenRecord,
    AuthUser,
    AuthenticatedActor,
    IssuedAccessToken,
    utc_now,
)
from deepclaw.web_backend.auth.security import hash_token
from deepclaw.utils.db import build_async_sessionmaker, create_async_engine_from_url
from deepclaw.web_backend.db import resolve_metadata_db_url, should_import_home_sqlite

LEGACY_HOME_NAME = ".langchain_api"
AUTH_MIGRATION_MARKER = ".auth_migrated_from_langchain_api"
AUTH_METADATA_IMPORT_MARKER = ".auth_imported_to_metadata_db"
# 令牌「最近使用时间」的写入节流窗口：同一令牌在窗口内重复校验不再写库，
# 避免每个带令牌的请求都产生一次 UPDATE + commit。
ACCESS_TOKEN_LAST_USED_THROTTLE = timedelta(seconds=60)


def _get_auth_db_path(base_path: Path) -> Path:
    return base_path / "auth.db"


def _table_exists(connection: sqlite3.Connection, table_name: str) -> bool:
    row = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    return row is not None


def _get_table_columns(connection: sqlite3.Connection, table_name: str) -> list[str]:
    rows = connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    return [str(row[1]) for row in rows]


def _deserialize_datetime_value(value):
    if value is None or isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value)
    return value


def _merge_table_rows(
    *,
    legacy_connection: sqlite3.Connection,
    current_connection: sqlite3.Connection,
    table_name: str,
    identity_columns: list[str],
) -> None:
    if not _table_exists(legacy_connection, table_name) or not _table_exists(
        current_connection, table_name
    ):
        return

    columns = _get_table_columns(legacy_connection, table_name)
    if not columns:
        return

    writable_columns = [column for column in columns if column != "id"]
    select_sql = f"SELECT {', '.join(columns)} FROM {table_name}"
    for row in legacy_connection.execute(select_sql).fetchall():
        row_data = dict(zip(columns, row, strict=False))
        identity_values = [row_data[column] for column in identity_columns]
        where_clause = " AND ".join(f"{column} = ?" for column in identity_columns)
        existing_row = current_connection.execute(
            f"SELECT id FROM {table_name} WHERE {where_clause}",
            identity_values,
        ).fetchone()

        if existing_row is None:
            placeholders = ", ".join("?" for _ in writable_columns)
            current_connection.execute(
                f"""
                INSERT INTO {table_name} ({', '.join(writable_columns)})
                VALUES ({placeholders})
                """,
                [row_data[column] for column in writable_columns],
            )
            continue

        set_clause = ", ".join(f"{column} = ?" for column in writable_columns)
        current_connection.execute(
            f"""
            UPDATE {table_name}
            SET {set_clause}
            WHERE {where_clause}
            """,
            [row_data[column] for column in writable_columns] + identity_values,
        )


def _backfill_username_from_email(connection: sqlite3.Connection) -> None:
    """把旧库中为空的 username 回填为邮箱，保证并入新库后仍可登录。

    Args:
        connection: 旧库 sqlite 连接。
    """
    columns = _get_table_columns(connection, "authuser")
    if "username" not in columns or "email" not in columns:
        return
    connection.execute(
        "UPDATE authuser SET username = email WHERE username IS NULL AND email IS NOT NULL"
    )

def _merge_legacy_auth_db(legacy_db_path: Path, current_db_path: Path) -> None:
    with sqlite3.connect(legacy_db_path) as legacy_connection, sqlite3.connect(
        current_db_path
    ) as current_connection:
        # 新版以 username 作为唯一登录标识；旧库没有该列时按 email 判重。
        legacy_columns = _get_table_columns(legacy_connection, "authuser")
        if "username" in legacy_columns:
            _backfill_username_from_email(legacy_connection)
            identity_columns = ["username"]
        else:
            identity_columns = ["email"]
        _merge_table_rows(
            legacy_connection=legacy_connection,
            current_connection=current_connection,
            table_name="authuser",
            identity_columns=identity_columns,
        )
        _merge_table_rows(
            legacy_connection=legacy_connection,
            current_connection=current_connection,
            table_name="accesstokenrecord",
            identity_columns=["token_hash"],
        )
        current_connection.commit()


def migrate_legacy_auth_db_if_needed(current_home_path: Path) -> None:
    marker_path = current_home_path / AUTH_MIGRATION_MARKER
    if marker_path.exists():
        return

    legacy_home_path = current_home_path.parent / LEGACY_HOME_NAME
    legacy_db_path = _get_auth_db_path(legacy_home_path)
    if not legacy_db_path.exists():
        return

    current_home_path.mkdir(parents=True, exist_ok=True)
    current_db_path = _get_auth_db_path(current_home_path)

    if not current_db_path.exists():
        shutil.copy2(legacy_db_path, current_db_path)
    else:
        _merge_legacy_auth_db(legacy_db_path, current_db_path)

    marker_path.write_text("migrated\n", encoding="utf-8")


# SQLite 不支持直接修改列约束，改用重建表的方式放宽 email 的 NOT NULL。
AUTH_USER_TABLE_DDL = (
    "CREATE TABLE authuser ("
    "id INTEGER NOT NULL PRIMARY KEY, "
    "user_id VARCHAR NOT NULL UNIQUE, "
    "username VARCHAR UNIQUE, "
    "email VARCHAR, "
    "password_hash VARCHAR NOT NULL, "
    "role VARCHAR NOT NULL, "
    "is_active BOOLEAN NOT NULL, "
    "created_at TIMESTAMP NOT NULL, "
    "updated_at TIMESTAMP NOT NULL"
    ")"
)


async def _relax_email_not_null(conn) -> None:
    """把 authuser.email 的 NOT NULL 约束放宽为可空。

    SQLite 需要重建表，PostgreSQL 可以直接 ALTER COLUMN。

    Args:
        conn: 当前异步数据库连接。
    """
    dialect = conn.dialect.name
    if dialect == "postgresql":
        await conn.execute(
            text("ALTER TABLE authuser ALTER COLUMN email DROP NOT NULL")
        )
        return
    if dialect != "sqlite":
        return
    table_info = await conn.exec_driver_sql("PRAGMA table_info(authuser)")
    columns = table_info.fetchall()
    email_column = next((row for row in columns if row[1] == "email"), None)
    if email_column is None or not email_column[3]:
        return
    await conn.exec_driver_sql("ALTER TABLE authuser RENAME TO authuser_legacy_email")
    await conn.exec_driver_sql(AUTH_USER_TABLE_DDL)
    column_names = ", ".join(row[1] for row in columns)
    await conn.exec_driver_sql(
        f"INSERT INTO authuser ({column_names}) SELECT {column_names} FROM authuser_legacy_email"
    )
    await conn.exec_driver_sql("DROP TABLE authuser_legacy_email")


class AuthStore:
    def __init__(self, db_url: str | None = None):
        should_import_home_db = db_url is None
        if db_url is None:
            db_url = resolve_metadata_db_url()
            if db_url.startswith("postgresql"):
                migrate_legacy_auth_db_if_needed(HOME_PATH)

        self.db_url = db_url
        self.engine = create_async_engine_from_url(db_url)
        self.async_session = build_async_sessionmaker(self.engine)
        self._init_done = False
        self._sqlite_import_path = (
            should_import_home_sqlite(
                filename="auth.db",
                target_db_url=self.db_url,
            )
            if should_import_home_db
            else None
        )
        self._sqlite_import_marker = Path(HOME_PATH) / AUTH_METADATA_IMPORT_MARKER

    async def _ensure_init(self):
        if self._init_done:
            return
        from sqlmodel import SQLModel
        async with self.engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.create_all)
        await self._migrate_legacy_schema()
        await self._import_home_sqlite_if_needed()
        self._init_done = True

    async def _migrate_legacy_schema(self) -> None:
        """为旧库补齐 username 列，并把历史邮箱回填为用户名。

        旧版本以邮箱作为唯一登录标识，升级后邮箱变为可选资料；
        这里把存量邮箱复制到 username，保证老账号仍能登录。

        Args:
            无。
        """
        async with self.engine.begin() as conn:
            columns = await conn.run_sync(
                lambda sync_conn: {
                    column["name"]
                    for column in inspect(sync_conn).get_columns("authuser")
                }
            )
            if "username" not in columns:
                await conn.execute(
                    text("ALTER TABLE authuser ADD COLUMN username VARCHAR")
                )
            if "email" in columns:
                # 旧库 email 为 NOT NULL：先回填再放宽约束，否则 username-only 账号无法写入。
                await conn.execute(
                    text(
                        "UPDATE authuser SET email = username "
                        "WHERE email IS NULL AND username IS NOT NULL"
                    )
                )
                await _relax_email_not_null(conn)
                await conn.execute(
                    text(
                        "UPDATE authuser SET username = email "
                        "WHERE username IS NULL AND email IS NOT NULL"
                    )
                )

    async def _import_home_sqlite_if_needed(self) -> None:
        if self._sqlite_import_path is None or self._sqlite_import_marker.exists():
            return

        with sqlite3.connect(self._sqlite_import_path) as connection:
            connection.row_factory = sqlite3.Row
            user_rows = connection.execute("SELECT * FROM authuser").fetchall()
            token_rows = connection.execute("SELECT * FROM accesstokenrecord").fetchall()

        async with self.async_session() as session:
            for row in user_rows:
                payload = dict(row)
                for column in ["created_at", "updated_at"]:
                    payload[column] = _deserialize_datetime_value(payload[column])
                # 用户名是唯一登录标识，导入时按 username 判重；
                # 历史数据没有 username 时回退用 email 作为用户名。
                legacy_username = payload.get("username") or payload.get("email")
                payload["username"] = legacy_username
                result = await session.exec(
                    select(AuthUser).where(AuthUser.username == legacy_username)
                )
                model = result.first()
                if model is None:
                    model = AuthUser(**{k: v for k, v in payload.items() if k != "id"})
                else:
                    for key, value in payload.items():
                        if key != "id":
                            setattr(model, key, value)
                session.add(model)

            for row in token_rows:
                payload = dict(row)
                for column in ["expires_at", "last_used_at", "created_at"]:
                    payload[column] = _deserialize_datetime_value(payload[column])
                result = await session.exec(
                    select(AccessTokenRecord).where(
                        AccessTokenRecord.token_hash == payload["token_hash"]
                    )
                )
                model = result.first()
                if model is None:
                    model = AccessTokenRecord(
                        **{k: v for k, v in payload.items() if k != "id"}
                    )
                else:
                    for key, value in payload.items():
                        if key != "id":
                            setattr(model, key, value)
                session.add(model)

            await session.commit()

        self._sqlite_import_marker.write_text("imported\n", encoding="utf-8")

    async def reconcile_access_token_expiry(self, *, expire_days: int) -> None:
        await self._ensure_init()
        max_lifetime = timedelta(days=expire_days)
        now = utc_now()
        async with self.async_session() as session:
            result = await session.exec(select(AccessTokenRecord))
            records = list(result.all())
            changed = False
            for record in records:
                normalized_expires_at = min(
                    record.expires_at,
                    record.created_at + max_lifetime,
                )
                if normalized_expires_at <= now:
                    await session.delete(record)
                    changed = True
                    continue
                if normalized_expires_at != record.expires_at:
                    record.expires_at = normalized_expires_at
                    session.add(record)
                    changed = True

            if changed:
                await session.commit()

    async def get_user_by_username(self, username: str) -> AuthUser | None:
        """按用户名查询用户。

        Args:
            username: 已归一化的登录用户名。

        Returns:
            AuthUser | None: 匹配用户，不存在时返回 None。
        """
        await self._ensure_init()
        async with self.async_session() as session:
            result = await session.exec(
                select(AuthUser).where(AuthUser.username == username)
            )
            return result.first()

    async def get_user_by_email(self, email: str) -> AuthUser | None:
        """按邮箱查询用户，仅用于兼容历史数据。

        Args:
            email: 归一化邮箱。

        Returns:
            AuthUser | None: 匹配用户，不存在时返回 None。
        """
        await self._ensure_init()
        async with self.async_session() as session:
            result = await session.exec(
                select(AuthUser).where(AuthUser.email == email)
            )
            return result.first()

    async def get_user_by_user_id(self, user_id: str) -> AuthUser | None:
        await self._ensure_init()
        async with self.async_session() as session:
            result = await session.exec(
                select(AuthUser).where(AuthUser.user_id == user_id)
            )
            return result.first()

    async def has_admin_user(self) -> bool:
        await self._ensure_init()
        async with self.async_session() as session:
            result = await session.exec(
                select(AuthUser).where(AuthUser.role == "admin")
            )
            return result.first() is not None

    async def count_admin_users(self) -> int:
        """统计管理员账号数量。

        Returns:
            int: 管理员账号数量。
        """
        await self._ensure_init()
        async with self.async_session() as session:
            result = await session.exec(select(AuthUser).where(AuthUser.role == "admin"))
            return len(result.all())

    async def count_active_admin_users(self) -> int:
        """统计启用中的管理员账号数量。

        Returns:
            int: 启用中的管理员数量。
        """
        await self._ensure_init()
        async with self.async_session() as session:
            result = await session.exec(
                select(AuthUser).where(AuthUser.role == "admin", AuthUser.is_active.is_(True))
            )
            return len(result.all())

    async def create_user(
        self,
        *,
        username: str,
        password_hash: str,
        role: str,
        email: str | None = None,
    ) -> AuthUser:
        """创建用户账号。

        Args:
            username: 登录用户名。
            password_hash: 密码哈希。
            role: 用户角色。
            email: 可选邮箱。

        Returns:
            AuthUser: 已创建的账号。
        """
        await self._ensure_init()
        async with self.async_session() as session:
            now = utc_now()
            if email is not None:
                email_taken = (
                    await session.exec(select(AuthUser).where(AuthUser.email == email))
                ).first()
                # 邮箱已不是登录标识，重复时不再阻止建号，直接不写入该可选字段。
                if email_taken is not None:
                    email = None
            user = AuthUser(
                user_id=f"user_{uuid.uuid4().hex}",
                username=username,
                email=email,
                password_hash=password_hash,
                role=role,
                is_active=True,
                created_at=now,
                updated_at=now,
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
            return user

    async def list_users(self, *, search: str = "") -> list[AuthUser]:
        await self._ensure_init()
        async with self.async_session() as session:
            statement = select(AuthUser).order_by(AuthUser.created_at.desc())
            if search:
                like = f"%{search}%"
                statement = statement.where(
                    (AuthUser.username.like(like)) | (AuthUser.email.like(like))
                )
            result = await session.exec(statement)
            return list(result.all())

    async def update_user_role(self, *, user_id: str, role: str) -> AuthUser:
        await self._ensure_init()
        async with self.async_session() as session:
            result = await session.exec(
                select(AuthUser).where(AuthUser.user_id == user_id)
            )
            user = result.first()
            if user is None:
                raise BusinessRuleError("用户不存在。")
            user.role = role
            user.updated_at = utc_now()
            session.add(user)
            await session.commit()
            await session.refresh(user)
            return user

    async def update_user_status(self, *, user_id: str, is_active: bool) -> AuthUser:
        await self._ensure_init()
        async with self.async_session() as session:
            result = await session.exec(
                select(AuthUser).where(AuthUser.user_id == user_id)
            )
            user = result.first()
            if user is None:
                raise BusinessRuleError("用户不存在。")
            user.is_active = is_active
            user.updated_at = utc_now()
            session.add(user)
            await session.commit()
            await session.refresh(user)
            return user

    async def update_user_profile(
        self,
        *,
        user_id: str,
        username: str | None = None,
        email: str | None = None,
    ) -> AuthUser:
        """更新用户用户名与邮箱。

        Args:
            user_id: 目标用户 ID。
            username: 新用户名；为 None 表示不修改。
            email: 新邮箱；为 None 表示不修改，空字符串由上层转换为清空。

        Returns:
            AuthUser: 更新后的账号。

        Raises:
            BusinessRuleError: 用户不存在时抛出。
        """
        await self._ensure_init()
        async with self.async_session() as session:
            result = await session.exec(
                select(AuthUser).where(AuthUser.user_id == user_id)
            )
            user = result.first()
            if user is None:
                raise BusinessRuleError("用户不存在。")
            if username is not None:
                user.username = username
            if email is not None:
                user.email = email
            user.updated_at = utc_now()
            session.add(user)
            await session.commit()
            await session.refresh(user)
            return user

    async def delete_user(self, *, user_id: str) -> bool:
        """删除用户账号。

        Args:
            user_id: 目标用户 ID。

        Returns:
            bool: 删除成功返回真，账号不存在返回假。
        """
        await self._ensure_init()
        async with self.async_session() as session:
            result = await session.exec(
                select(AuthUser).where(AuthUser.user_id == user_id)
            )
            user = result.first()
            if user is None:
                return False
            await session.delete(user)
            await session.commit()
            return True

    async def update_user_password(self, *, user_id: str, password_hash: str) -> AuthUser:
        await self._ensure_init()
        async with self.async_session() as session:
            result = await session.exec(
                select(AuthUser).where(AuthUser.user_id == user_id)
            )
            user = result.first()
            if user is None:
                raise BusinessRuleError("用户不存在。")
            user.password_hash = password_hash
            user.updated_at = utc_now()
            session.add(user)
            await session.commit()
            await session.refresh(user)
            return user

    async def revoke_token(self, token: str) -> bool:
        await self._ensure_init()
        token_hash_value = hash_token(token)
        async with self.async_session() as session:
            result = await session.exec(
                select(AccessTokenRecord).where(AccessTokenRecord.token_hash == token_hash_value)
            )
            record = result.first()
            if record is None:
                return False
            await session.delete(record)
            await session.commit()
            return True

    async def revoke_tokens_by_user_id(self, user_id: str) -> int:
        await self._ensure_init()
        async with self.async_session() as session:
            result = await session.exec(
                select(AccessTokenRecord).where(AccessTokenRecord.user_id == user_id)
            )
            records = list(result.all())
            for record in records:
                await session.delete(record)
            await session.commit()
            return len(records)

    async def issue_access_token(
        self,
        *,
        user: AuthUser,
        raw_token: str,
        expire_days: int,
    ) -> IssuedAccessToken:
        await self._ensure_init()
        async with self.async_session() as session:
            now = utc_now()
            record = AccessTokenRecord(
                user_id=user.user_id,
                token_hash=hash_token(raw_token),
                expires_at=now + timedelta(days=expire_days),
                last_used_at=now,
                created_at=now,
            )
            session.add(record)
            await session.commit()
            await session.refresh(record)
            return IssuedAccessToken(token=raw_token, user=user, record=record)

    async def get_actor_by_token(self, token: str) -> AuthenticatedActor:
        await self._ensure_init()
        token_hash_value = hash_token(token)
        async with self.async_session() as session:
            result = await session.exec(
                select(AccessTokenRecord).where(
                    AccessTokenRecord.token_hash == token_hash_value
                )
            )
            record = result.first()
            if record is None:
                raise BusinessRuleError("登录状态已失效，请重新登录。")
            if record.expires_at <= utc_now():
                await session.delete(record)
                await session.commit()
                raise BusinessRuleError("登录状态已失效，请重新登录。")

            result = await session.exec(
                select(AuthUser).where(AuthUser.user_id == record.user_id)
            )
            user = result.first()
            if user is None:
                raise BusinessRuleError("登录状态已失效，请重新登录。")

            now = utc_now()
            if (
                record.last_used_at is None
                or now - record.last_used_at >= ACCESS_TOKEN_LAST_USED_THROTTLE
            ):
                record.last_used_at = now
                session.add(record)
                await session.commit()
                await session.refresh(record)

            await session.refresh(user)
            return AuthenticatedActor(user=user, record=record)
