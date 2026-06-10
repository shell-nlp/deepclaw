import os
import uuid
from typing import Optional

from sqlalchemy import inspect, or_, text
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

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
from deepclaw.constant import home_path


VALID_REPLY_MODES = {"final", "streaming"}
VALID_MESSAGE_STATUSES = {"received", "processing", "done", "failed"}


class ChannelStore:
    def __init__(self, db_url: Optional[str] = None):
        if db_url is None:
            os.makedirs(home_path, exist_ok=True)
            db_url = f"sqlite:///{os.path.join(home_path, 'channels.db')}"

        connect_args = {"check_same_thread": False} if db_url.startswith("sqlite") else {}
        engine_kwargs = {"connect_args": connect_args}
        if db_url == "sqlite:///:memory:":
            engine_kwargs["poolclass"] = StaticPool

        self.engine = create_engine(db_url, echo=False, **engine_kwargs)
        SQLModel.metadata.create_all(self.engine)
        self._ensure_channel_session_schema()
        self._ensure_channel_binding_schema()

    def get_or_create_user(
        self,
        *,
        channel: str,
        channel_user_id: str,
        user_id: str | None = None,
        display_name: str | None = None,
    ) -> ChannelUser:
        with Session(self.engine) as session:
            statement = select(ChannelUser).where(
                ChannelUser.channel == channel,
                ChannelUser.channel_user_id == channel_user_id,
            )
            existing = session.exec(statement).first()
            if existing is not None:
                if user_id and existing.user_id != user_id:
                    existing.user_id = user_id
                    existing.updated_at = utc_now()
                    session.add(existing)
                    session.commit()
                    session.refresh(existing)
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
            session.commit()
            session.refresh(user)
            return user

    def get_or_create_session(
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
        with Session(self.engine) as session:
            statement = select(ChannelSession).where(
                ChannelSession.channel == channel,
                ChannelSession.channel_conversation_id == channel_conversation_id,
                ChannelSession.channel_user_id == channel_user_id,
            )
            existing = session.exec(statement).first()
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
                    session.commit()
                    session.refresh(existing)
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
            session.commit()
            session.refresh(channel_session)
            return channel_session

    def create_binding(
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
        now = utc_now()
        with Session(self.engine) as session:
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
            session.commit()
            session.refresh(binding)
            return binding

    def get_binding(self, binding_id: int | None) -> ChannelBinding | None:
        if binding_id is None:
            return None
        with Session(self.engine) as session:
            return session.get(ChannelBinding, binding_id)

    def upsert_binding(
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
        with Session(self.engine) as session:
            statement = select(ChannelBinding).where(
                ChannelBinding.channel == channel,
                ChannelBinding.owner_user_id == owner_user_id,
            )
            binding = session.exec(statement).first()
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
            session.commit()
            session.refresh(binding)
            return binding

    def list_bindings(
        self,
        *,
        channel: str | None = None,
        owner_user_id: str | None = None,
        manager_user_id: str | None = None,
        participant_user_id: str | None = None,
    ) -> list[ChannelBinding]:
        with Session(self.engine) as session:
            statement = select(ChannelBinding).order_by(ChannelBinding.updated_at.desc())
            if channel is not None:
                statement = statement.where(ChannelBinding.channel == channel)
            if owner_user_id is not None:
                statement = statement.where(ChannelBinding.owner_user_id == owner_user_id)
            if manager_user_id is not None:
                statement = statement.where(ChannelBinding.manager_user_id == manager_user_id)
            if participant_user_id is not None:
                # 绑定协作模式下，owner 与 manager 都应能看到该记录。
                statement = statement.where(
                    or_(
                        ChannelBinding.owner_user_id == participant_user_id,
                        ChannelBinding.manager_user_id == participant_user_id,
                    )
                )
            return list(session.exec(statement).all())

    def delete_binding(self, binding_id: int) -> bool:
        with Session(self.engine) as session:
            binding = session.get(ChannelBinding, binding_id)
            if binding is None:
                return False
            session.delete(binding)
            session.commit()
            return True

    def update_binding(
        self,
        binding_id: int,
        *,
        display_name: str | None = None,
        credentials: dict | None = None,
        config: dict | None = None,
        runtime_state: dict | None = None,
        status: str | None = None,
    ) -> ChannelBinding:
        with Session(self.engine) as session:
            binding = session.get(ChannelBinding, binding_id)
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
            session.commit()
            session.refresh(binding)
            return binding

    def update_binding_runtime_state(
        self,
        binding_id: int,
        runtime_state: dict,
    ) -> ChannelBinding:
        with Session(self.engine) as session:
            binding = session.get(ChannelBinding, binding_id)
            if binding is None:
                raise ValueError("Channel binding not found")
            binding.runtime_state = dict(runtime_state)
            binding.updated_at = utc_now()
            session.add(binding)
            session.commit()
            session.refresh(binding)
            return binding

    def get_or_create_message_record(
        self, message: ChannelMessage
    ) -> ChannelMessageRecord:
        with Session(self.engine) as session:
            statement = select(ChannelMessageRecord).where(
                ChannelMessageRecord.channel == message.channel,
                ChannelMessageRecord.message_id == message.message_id,
            )
            existing = session.exec(statement).first()
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
            session.commit()
            session.refresh(record)
            return record

    def mark_message_status(
        self,
        channel: str,
        message_id: str,
        status: MessageStatus,
        *,
        error: str | None = None,
    ) -> ChannelMessageRecord:
        if status not in VALID_MESSAGE_STATUSES:
            raise ValueError(f"Invalid message status: {status}")

        with Session(self.engine) as session:
            statement = select(ChannelMessageRecord).where(
                ChannelMessageRecord.channel == channel,
                ChannelMessageRecord.message_id == message_id,
            )
            record = session.exec(statement).first()
            if record is None:
                raise ValueError("Channel message record not found")

            record.status = status
            record.error = error
            record.updated_at = utc_now()
            session.add(record)
            session.commit()
            session.refresh(record)
            return record

    def get_runtime_state(
        self,
        *,
        channel: str,
        state_key: str = "default",
    ) -> ChannelRuntimeState | None:
        with Session(self.engine) as session:
            statement = select(ChannelRuntimeState).where(
                ChannelRuntimeState.channel == channel,
                ChannelRuntimeState.state_key == state_key,
            )
            return session.exec(statement).first()

    def list_runtime_states(
        self,
        *,
        channel: str | None = None,
    ) -> list[ChannelRuntimeState]:
        with Session(self.engine) as session:
            statement = select(ChannelRuntimeState)
            if channel is not None:
                statement = statement.where(ChannelRuntimeState.channel == channel)
            statement = statement.order_by(ChannelRuntimeState.state_key)
            return list(session.exec(statement).all())

    def upsert_runtime_state(
        self,
        *,
        channel: str,
        state_key: str = "default",
        data: dict,
    ) -> ChannelRuntimeState:
        with Session(self.engine) as session:
            statement = select(ChannelRuntimeState).where(
                ChannelRuntimeState.channel == channel,
                ChannelRuntimeState.state_key == state_key,
            )
            runtime_state = session.exec(statement).first()
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
            session.commit()
            session.refresh(runtime_state)
            return runtime_state

    def delete_runtime_state(
        self,
        *,
        channel: str,
        state_key: str = "default",
    ) -> bool:
        with Session(self.engine) as session:
            statement = select(ChannelRuntimeState).where(
                ChannelRuntimeState.channel == channel,
                ChannelRuntimeState.state_key == state_key,
            )
            runtime_state = session.exec(statement).first()
            if runtime_state is None:
                return False

            session.delete(runtime_state)
            session.commit()
            return True

    def list_sessions(self, manager_user_id: str | None = None) -> list[ChannelSession]:
        with Session(self.engine) as session:
            statement = select(ChannelSession).order_by(ChannelSession.updated_at.desc())
            if manager_user_id is not None:
                statement = statement.where(
                    ChannelSession.manager_user_id == manager_user_id
                )
            return list(session.exec(statement).all())

    def get_session_by_session_id(self, session_id: str) -> ChannelSession | None:
        with Session(self.engine) as session:
            statement = select(ChannelSession).where(
                ChannelSession.session_id == session_id
            )
            return session.exec(statement).first()

    def update_session_reply_mode(
        self, session_id: str, reply_mode: ReplyMode
    ) -> ChannelSession:
        self._validate_reply_mode(reply_mode)
        with Session(self.engine) as session:
            statement = select(ChannelSession).where(
                ChannelSession.session_id == session_id
            )
            channel_session = session.exec(statement).first()
            if channel_session is None:
                raise ValueError("Channel session not found")

            channel_session.reply_mode = reply_mode
            channel_session.updated_at = utc_now()
            session.add(channel_session)
            session.commit()
            session.refresh(channel_session)
            return channel_session

    @staticmethod
    def _validate_reply_mode(reply_mode: str) -> None:
        if reply_mode not in VALID_REPLY_MODES:
            raise ValueError(f"Invalid reply_mode: {reply_mode}")

    def _ensure_channel_session_schema(self) -> None:
        inspector = inspect(self.engine)
        try:
            columns = {column["name"] for column in inspector.get_columns("channel_sessions")}
        except Exception:
            return

        if "manager_user_id" in columns:
            return

        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "ALTER TABLE channel_sessions "
                    "ADD COLUMN manager_user_id VARCHAR"
                )
            )
            connection.execute(
                text(
                    "UPDATE channel_sessions "
                    "SET manager_user_id = user_id "
                    "WHERE manager_user_id IS NULL OR manager_user_id = ''"
                )
            )

    def _ensure_channel_binding_schema(self) -> None:
        inspector = inspect(self.engine)
        try:
            columns = {column["name"] for column in inspector.get_columns("channel_sessions")}
        except Exception:
            return

        if "binding_id" in columns:
            return

        with self.engine.begin() as connection:
            connection.execute(
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
