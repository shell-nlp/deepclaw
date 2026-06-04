import os
import uuid
from typing import Optional

from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from langchain_api.channels.models import (
    ChannelMessage,
    ChannelMessageRecord,
    ChannelRuntimeState,
    ChannelSession,
    ChannelUser,
    MessageStatus,
    ReplyMode,
    utc_now,
)
from langchain_api.constant import home_path


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
                return existing

            now = utc_now()
            channel_session = ChannelSession(
                channel=channel,
                channel_conversation_id=channel_conversation_id,
                channel_user_id=channel_user_id,
                user_id=user_id,
                session_id=session_id or str(uuid.uuid4()),
                reply_mode=reply_mode,
                created_at=now,
                updated_at=now,
            )
            session.add(channel_session)
            session.commit()
            session.refresh(channel_session)
            return channel_session

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

    def list_sessions(self) -> list[ChannelSession]:
        with Session(self.engine) as session:
            statement = select(ChannelSession).order_by(ChannelSession.updated_at.desc())
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


_store: ChannelStore | None = None


def get_channel_store(db_url: Optional[str] = None) -> ChannelStore:
    global _store
    if _store is None or db_url is not None:
        _store = ChannelStore(db_url)
    return _store
