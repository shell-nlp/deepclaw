import os
import shutil
import sqlite3
import uuid
from datetime import timedelta
from pathlib import Path

from sqlmodel import select

from deepclaw.constant import home_path
from deepclaw.web_backend.auth.models import (
    AccessTokenRecord,
    AuthUser,
    AuthenticatedActor,
    IssuedAccessToken,
    utc_now,
)
from deepclaw.web_backend.auth.security import hash_token
from deepclaw.web_backend.db import build_async_sessionmaker, create_async_engine_from_url

LEGACY_HOME_NAME = ".langchain_api"
AUTH_MIGRATION_MARKER = ".auth_migrated_from_langchain_api"


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


def _merge_legacy_auth_db(legacy_db_path: Path, current_db_path: Path) -> None:
    with sqlite3.connect(legacy_db_path) as legacy_connection, sqlite3.connect(
        current_db_path
    ) as current_connection:
        _merge_table_rows(
            legacy_connection=legacy_connection,
            current_connection=current_connection,
            table_name="authuser",
            identity_columns=["email"],
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


class AuthStore:
    def __init__(self, db_url: str | None = None):
        if db_url is None:
            migrate_legacy_auth_db_if_needed(home_path)
            os.makedirs(home_path, exist_ok=True)
            db_url = f"sqlite:///{os.path.join(home_path, 'auth.db')}"

        self.engine = create_async_engine_from_url(db_url)
        self.async_session = build_async_sessionmaker(self.engine)
        self._init_done = False

    async def _ensure_init(self):
        if self._init_done:
            return
        from sqlmodel import SQLModel
        async with self.engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.create_all)
        self._init_done = True

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

    async def get_user_by_email(self, email: str) -> AuthUser | None:
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

    async def create_user(self, *, email: str, password_hash: str, role: str) -> AuthUser:
        await self._ensure_init()
        async with self.async_session() as session:
            now = utc_now()
            user = AuthUser(
                user_id=f"user_{uuid.uuid4().hex}",
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
                statement = statement.where(AuthUser.email.like(like))
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
                raise ValueError("用户不存在。")
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
                raise ValueError("用户不存在。")
            user.is_active = is_active
            user.updated_at = utc_now()
            session.add(user)
            await session.commit()
            await session.refresh(user)
            return user

    async def update_user_password(self, *, user_id: str, password_hash: str) -> AuthUser:
        await self._ensure_init()
        async with self.async_session() as session:
            result = await session.exec(
                select(AuthUser).where(AuthUser.user_id == user_id)
            )
            user = result.first()
            if user is None:
                raise ValueError("用户不存在。")
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
                raise ValueError("登录状态已失效，请重新登录。")
            if record.expires_at <= utc_now():
                await session.delete(record)
                await session.commit()
                raise ValueError("登录状态已失效，请重新登录。")

            result = await session.exec(
                select(AuthUser).where(AuthUser.user_id == record.user_id)
            )
            user = result.first()
            if user is None:
                raise ValueError("登录状态已失效，请重新登录。")

            record.last_used_at = utc_now()
            session.add(record)
            await session.commit()
            await session.refresh(record)
            await session.refresh(user)
            return AuthenticatedActor(user=user, record=record)
