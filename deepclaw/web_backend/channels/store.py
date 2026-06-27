import json
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from sqlmodel import or_, select, text

from deepclaw.web_backend.channels.models import (
    ChannelBinding,
    ChannelMessage,
    ChannelMessageRecord,
    ChannelRuntimeState,
    ChannelSession,
    ChannelUser,
    MessageStatus,
    ReplyMode,
    utc_now,
)
from deepclaw.web_backend.db import (
    build_async_sessionmaker,
    create_async_engine_from_url,
    resolve_metadata_db_url,
    should_import_home_sqlite,
)
from deepclaw.constant import home_path


VALID_REPLY_MODES = {"final", "streaming"}
VALID_MESSAGE_STATUSES = {"received", "processing", "done", "failed"}
CHANNELS_METADATA_IMPORT_MARKER = ".channels_imported_to_metadata_db"


def _sqlite_table_exists(connection: sqlite3.Connection, table_name: str) -> bool:
    row = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    return row is not None


def _deserialize_json_value(value):
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def _deserialize_datetime_value(value):
    if value is None or isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value)
    return value


class ChannelStore:
    def __init__(self, db_url: Optional[str] = None):
        should_import_home_db = db_url is None
        if db_url is None:
            db_url = resolve_metadata_db_url("channels.db")

        self.db_url = db_url
        self.engine = create_async_engine_from_url(db_url)
        self.async_session = build_async_sessionmaker(self.engine)
        self._init_done = False
        self._sqlite_import_path = (
            should_import_home_sqlite(
                filename="channels.db",
                target_db_url=self.db_url,
            )
            if should_import_home_db
            else None
        )
        self._sqlite_import_marker = Path(home_path) / CHANNELS_METADATA_IMPORT_MARKER

    async def _ensure_init(self):
        if self._init_done:
            return
        from sqlmodel import SQLModel
        async with self.engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.create_all)
        await self._ensure_channel_session_schema()
        await self._ensure_channel_binding_schema()
        await self._import_home_sqlite_if_needed()
        self._init_done = True

    async def _import_home_sqlite_if_needed(self) -> None:
        if self._sqlite_import_path is None or self._sqlite_import_marker.exists():
            return

        table_specs = [
            (ChannelUser, "channel_users", ["channel", "channel_user_id"], []),
            (
                ChannelSession,
                "channel_sessions",
                ["channel", "channel_conversation_id", "channel_user_id"],
                [],
            ),
            (
                ChannelMessageRecord,
                "channel_message_records",
                ["channel", "message_id"],
                [],
            ),
            (
                ChannelRuntimeState,
                "channel_runtime_states",
                ["channel", "state_key"],
                ["data"],
            ),
            (
                ChannelBinding,
                "channel_bindings",
                ["id"],
                ["credentials", "config", "runtime_state"],
            ),
        ]

        async with self.async_session() as session:
            with sqlite3.connect(self._sqlite_import_path) as connection:
                connection.row_factory = sqlite3.Row
                for model_class, table_name, identity_columns, json_columns in table_specs:
                    if not _sqlite_table_exists(connection, table_name):
                        continue
                    rows = connection.execute(f"SELECT * FROM {table_name}").fetchall()
                    for row in rows:
                        payload = dict(row)
                        for column in ["created_at", "updated_at"]:
                            if column in payload:
                                payload[column] = _deserialize_datetime_value(
                                    payload[column]
                                )
                        for column in json_columns:
                            if column in payload:
                                payload[column] = _deserialize_json_value(payload[column])
                        result = await session.exec(
                            select(model_class).where(
                                *[
                                    getattr(model_class, column) == payload[column]
                                    for column in identity_columns
                                ]
                            )
                        )
                        model = result.first()
                        if model is None:
                            model = model_class(**{k: v for k, v in payload.items() if k != "id"})
                        else:
                            for key, value in payload.items():
                                if key != "id":
                                    setattr(model, key, value)
                        session.add(model)
                await session.commit()

        self._sqlite_import_marker.write_text("imported\n", encoding="utf-8")

    async def get_or_create_user(
        self,
        *,
        channel: str,
        channel_user_id: str,
        user_id: str | None = None,
        display_name: str | None = None,
    ) -> ChannelUser:
        await self._ensure_init()
        async with self.async_session() as session:
            result = await session.exec(
                select(ChannelUser).where(
                    ChannelUser.channel == channel,
                    ChannelUser.channel_user_id == channel_user_id,
                )
            )
            existing = result.first()
            if existing is not None:
                if user_id and existing.user_id != user_id:
                    existing.user_id = user_id
                    existing.updated_at = utc_now()
                    session.add(existing)
                    await session.commit()
                    await session.refresh(existing)
                return existing

            now = utc_now()
            user = ChannelUser(
                channel=channel,
                channel_user_id=channel_user_id,
                user_id=user_id or f"user_{uuid.uuid4().hex}",
                display_name=display_name,
                created_at=now,
                updated_at=now,
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
            return user

    async def get_or_create_session(
        self,
        *,
        channel: str,
        channel_conversation_id: str,
        channel_user_id: str,
        user_id: str,
        manager_user_id: str | None = None,
        binding_id: int | None = None,
        reply_mode: ReplyMode = "final",
        session_id: str | None = None,
    ) -> ChannelSession:
        self._validate_reply_mode(reply_mode)
        await self._ensure_init()
        async with self.async_session() as session:
            result = await session.exec(
                select(ChannelSession).where(
                    ChannelSession.channel == channel,
                    ChannelSession.channel_conversation_id == channel_conversation_id,
                    ChannelSession.channel_user_id == channel_user_id,
                )
            )
            existing = result.first()
            if existing is not None:
                changed = False
                if existing.user_id != user_id:
                    existing.user_id = user_id
                    changed = True
                if existing.binding_id != binding_id:
                    existing.binding_id = binding_id
                    changed = True
                next_manager_user_id = manager_user_id or existing.user_id
                if existing.manager_user_id != next_manager_user_id:
                    existing.manager_user_id = next_manager_user_id
                    changed = True
                if changed:
                    existing.updated_at = utc_now()
                    session.add(existing)
                    await session.commit()
                    await session.refresh(existing)
                return existing

            now = utc_now()
            channel_session = ChannelSession(
                channel=channel,
                channel_conversation_id=channel_conversation_id,
                channel_user_id=channel_user_id,
                user_id=user_id,
                manager_user_id=manager_user_id or user_id,
                binding_id=binding_id,
                session_id=session_id or str(uuid.uuid4()),
                reply_mode=reply_mode,
                created_at=now,
                updated_at=now,
            )
            session.add(channel_session)
            await session.commit()
            await session.refresh(channel_session)
            return channel_session

    async def create_binding(
        self,
        *,
        channel: str,
        owner_user_id: str,
        manager_user_id: str,
        credentials: dict,
        display_name: str | None = None,
        config: dict | None = None,
        runtime_state: dict | None = None,
        status: str = "active",
    ) -> ChannelBinding:
        await self._ensure_init()
        now = utc_now()
        async with self.async_session() as session:
            binding = ChannelBinding(
                channel=channel,
                owner_user_id=owner_user_id,
                manager_user_id=manager_user_id,
                status=status,
                display_name=display_name,
                credentials=dict(credentials),
                config=dict(config or {}),
                runtime_state=dict(runtime_state or {}),
                created_at=now,
                updated_at=now,
            )
            session.add(binding)
            await session.commit()
            await session.refresh(binding)
            return binding

    async def get_binding(self, binding_id: int | None) -> ChannelBinding | None:
        if binding_id is None:
            return None
        await self._ensure_init()
        async with self.async_session() as session:
            return await session.get(ChannelBinding, binding_id)

    async def upsert_binding(
        self,
        *,
        channel: str,
        owner_user_id: str,
        manager_user_id: str,
        credentials: dict | None = None,
        display_name: str | None = None,
        config: dict | None = None,
        runtime_state: dict | None = None,
        status: str = "active",
    ) -> ChannelBinding:
        await self._ensure_init()
        async with self.async_session() as session:
            result = await session.exec(
                select(ChannelBinding).where(
                    ChannelBinding.channel == channel,
                    ChannelBinding.owner_user_id == owner_user_id,
                )
            )
            binding = result.first()
            now = utc_now()
            if binding is None:
                binding = ChannelBinding(
                    channel=channel,
                    owner_user_id=owner_user_id,
                    manager_user_id=manager_user_id,
                    status=status,
                    display_name=display_name,
                    credentials=dict(credentials or {}),
                    config=dict(config or {}),
                    runtime_state=dict(runtime_state or {}),
                    created_at=now,
                    updated_at=now,
                )
            else:
                binding.manager_user_id = manager_user_id
                binding.status = status
                if display_name is not None:
                    binding.display_name = display_name
                if credentials is not None:
                    merged_credentials = dict(binding.credentials or {})
                    merged_credentials.update(credentials)
                    binding.credentials = merged_credentials
                if config is not None:
                    merged_config = dict(binding.config or {})
                    merged_config.update(config)
                    binding.config = merged_config
                if runtime_state is not None:
                    merged_runtime_state = dict(binding.runtime_state or {})
                    merged_runtime_state.update(runtime_state)
                    binding.runtime_state = merged_runtime_state
                binding.updated_at = now

            session.add(binding)
            await session.commit()
            await session.refresh(binding)
            return binding

    async def list_bindings(
        self,
        *,
        channel: str | None = None,
        owner_user_id: str | None = None,
        manager_user_id: str | None = None,
        participant_user_id: str | None = None,
    ) -> list[ChannelBinding]:
        await self._ensure_init()
        async with self.async_session() as session:
            statement = select(ChannelBinding).order_by(ChannelBinding.updated_at.desc())
            if channel is not None:
                statement = statement.where(ChannelBinding.channel == channel)
            if owner_user_id is not None:
                statement = statement.where(ChannelBinding.owner_user_id == owner_user_id)
            if manager_user_id is not None:
                statement = statement.where(ChannelBinding.manager_user_id == manager_user_id)
            if participant_user_id is not None:
                statement = statement.where(
                    or_(
                        ChannelBinding.owner_user_id == participant_user_id,
                        ChannelBinding.manager_user_id == participant_user_id,
                    )
                )
            result = await session.exec(statement)
            return list(result.all())

    async def delete_binding(self, binding_id: int) -> bool:
        await self._ensure_init()
        async with self.async_session() as session:
            binding = await session.get(ChannelBinding, binding_id)
            if binding is None:
                return False
            await session.delete(binding)
            await session.commit()
            return True

    async def update_binding(
        self,
        binding_id: int,
        *,
        display_name: str | None = None,
        credentials: dict | None = None,
        config: dict | None = None,
        runtime_state: dict | None = None,
        status: str | None = None,
    ) -> ChannelBinding:
        await self._ensure_init()
        async with self.async_session() as session:
            binding = await session.get(ChannelBinding, binding_id)
            if binding is None:
                raise ValueError("Channel binding not found")

            if display_name is not None:
                binding.display_name = display_name
            if credentials is not None:
                merged_credentials = dict(binding.credentials or {})
                merged_credentials.update(credentials)
                binding.credentials = merged_credentials
            if config is not None:
                merged_config = dict(binding.config or {})
                merged_config.update(config)
                binding.config = merged_config
            if runtime_state is not None:
                merged_runtime_state = dict(binding.runtime_state or {})
                merged_runtime_state.update(runtime_state)
                binding.runtime_state = merged_runtime_state
            if status is not None:
                binding.status = status

            binding.updated_at = utc_now()
            session.add(binding)
            await session.commit()
            await session.refresh(binding)
            return binding

    async def update_binding_runtime_state(
        self,
        binding_id: int,
        runtime_state: dict,
    ) -> ChannelBinding:
        await self._ensure_init()
        async with self.async_session() as session:
            binding = await session.get(ChannelBinding, binding_id)
            if binding is None:
                raise ValueError("Channel binding not found")
            binding.runtime_state = dict(runtime_state)
            binding.updated_at = utc_now()
            session.add(binding)
            await session.commit()
            await session.refresh(binding)
            return binding

    async def get_or_create_message_record(
        self, message: ChannelMessage
    ) -> ChannelMessageRecord:
        await self._ensure_init()
        async with self.async_session() as session:
            result = await session.exec(
                select(ChannelMessageRecord).where(
                    ChannelMessageRecord.channel == message.channel,
                    ChannelMessageRecord.message_id == message.message_id,
                )
            )
            existing = result.first()
            if existing is not None:
                return existing

            now = utc_now()
            record = ChannelMessageRecord(
                channel=message.channel,
                message_id=message.message_id,
                channel_conversation_id=message.channel_conversation_id,
                channel_user_id=message.channel_user_id,
                status="received",
                created_at=now,
                updated_at=now,
            )
            session.add(record)
            await session.commit()
            await session.refresh(record)
            return record

    async def mark_message_status(
        self,
        channel: str,
        message_id: str,
        status: MessageStatus,
        *,
        error: str | None = None,
    ) -> ChannelMessageRecord:
        if status not in VALID_MESSAGE_STATUSES:
            raise ValueError(f"Invalid message status: {status}")
        await self._ensure_init()
        async with self.async_session() as session:
            result = await session.exec(
                select(ChannelMessageRecord).where(
                    ChannelMessageRecord.channel == channel,
                    ChannelMessageRecord.message_id == message_id,
                )
            )
            record = result.first()
            if record is None:
                raise ValueError("Channel message record not found")

            record.status = status
            record.error = error
            record.updated_at = utc_now()
            session.add(record)
            await session.commit()
            await session.refresh(record)
            return record

    async def get_runtime_state(
        self,
        *,
        channel: str,
        state_key: str = "default",
    ) -> ChannelRuntimeState | None:
        await self._ensure_init()
        async with self.async_session() as session:
            result = await session.exec(
                select(ChannelRuntimeState).where(
                    ChannelRuntimeState.channel == channel,
                    ChannelRuntimeState.state_key == state_key,
                )
            )
            return result.first()

    async def list_runtime_states(
        self,
        *,
        channel: str | None = None,
    ) -> list[ChannelRuntimeState]:
        await self._ensure_init()
        async with self.async_session() as session:
            statement = select(ChannelRuntimeState)
            if channel is not None:
                statement = statement.where(ChannelRuntimeState.channel == channel)
            statement = statement.order_by(ChannelRuntimeState.state_key)
            result = await session.exec(statement)
            return list(result.all())

    async def upsert_runtime_state(
        self,
        *,
        channel: str,
        state_key: str = "default",
        data: dict,
    ) -> ChannelRuntimeState:
        await self._ensure_init()
        async with self.async_session() as session:
            result = await session.exec(
                select(ChannelRuntimeState).where(
                    ChannelRuntimeState.channel == channel,
                    ChannelRuntimeState.state_key == state_key,
                )
            )
            runtime_state = result.first()
            now = utc_now()
            if runtime_state is None:
                runtime_state = ChannelRuntimeState(
                    channel=channel,
                    state_key=state_key,
                    data=dict(data),
                    created_at=now,
                    updated_at=now,
                )
            else:
                merged = dict(runtime_state.data or {})
                merged.update(data)
                runtime_state.data = merged
                runtime_state.updated_at = now

            session.add(runtime_state)
            await session.commit()
            await session.refresh(runtime_state)
            return runtime_state

    async def delete_runtime_state(
        self,
        *,
        channel: str,
        state_key: str = "default",
    ) -> bool:
        await self._ensure_init()
        async with self.async_session() as session:
            result = await session.exec(
                select(ChannelRuntimeState).where(
                    ChannelRuntimeState.channel == channel,
                    ChannelRuntimeState.state_key == state_key,
                )
            )
            runtime_state = result.first()
            if runtime_state is None:
                return False

            await session.delete(runtime_state)
            await session.commit()
            return True

    async def list_sessions(self, manager_user_id: str | None = None) -> list[ChannelSession]:
        await self._ensure_init()
        async with self.async_session() as session:
            statement = select(ChannelSession).order_by(ChannelSession.updated_at.desc())
            if manager_user_id is not None:
                statement = statement.where(
                    ChannelSession.manager_user_id == manager_user_id
                )
            result = await session.exec(statement)
            return list(result.all())

    async def get_session_by_session_id(self, session_id: str) -> ChannelSession | None:
        await self._ensure_init()
        async with self.async_session() as session:
            result = await session.exec(
                select(ChannelSession).where(
                    ChannelSession.session_id == session_id
                )
            )
            return result.first()

    async def update_session_reply_mode(
        self, session_id: str, reply_mode: ReplyMode
    ) -> ChannelSession:
        self._validate_reply_mode(reply_mode)
        await self._ensure_init()
        async with self.async_session() as session:
            result = await session.exec(
                select(ChannelSession).where(
                    ChannelSession.session_id == session_id
                )
            )
            channel_session = result.first()
            if channel_session is None:
                raise ValueError("Channel session not found")

            channel_session.reply_mode = reply_mode
            channel_session.updated_at = utc_now()
            session.add(channel_session)
            await session.commit()
            await session.refresh(channel_session)
            return channel_session

    @staticmethod
    def _validate_reply_mode(reply_mode: str) -> None:
        if reply_mode not in VALID_REPLY_MODES:
            raise ValueError(f"Invalid reply_mode: {reply_mode}")

    async def _ensure_channel_session_schema(self) -> None:
        from sqlalchemy import inspect as sync_inspect
        async with self.engine.connect() as conn:
            inspector = await conn.run_sync(sync_inspect)
            try:
                columns = {column["name"] for column in inspector.get_columns("channel_sessions")}
            except Exception:
                return

            if "manager_user_id" in columns:
                return

            await conn.execute(
                text(
                    "ALTER TABLE channel_sessions "
                    "ADD COLUMN manager_user_id VARCHAR"
                )
            )
            await conn.execute(
                text(
                    "UPDATE channel_sessions "
                    "SET manager_user_id = user_id "
                    "WHERE manager_user_id IS NULL OR manager_user_id = ''"
                )
            )
            await conn.commit()

    async def _ensure_channel_binding_schema(self) -> None:
        from sqlalchemy import inspect as sync_inspect
        async with self.engine.connect() as conn:
            inspector = await conn.run_sync(sync_inspect)
            try:
                columns = {column["name"] for column in inspector.get_columns("channel_sessions")}
            except Exception:
                return

            if "binding_id" in columns:
                return

            await conn.execute(
                text(
                    "ALTER TABLE channel_sessions "
                    "ADD COLUMN binding_id INTEGER"
                )
            )


_store: ChannelStore | None = None


def get_channel_store(db_url: Optional[str] = None) -> ChannelStore:
    global _store
    if _store is None or db_url is not None:
        _store = ChannelStore(db_url)
    return _store
