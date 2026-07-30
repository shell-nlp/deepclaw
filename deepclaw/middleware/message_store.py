"""按线程保存完整消息列表的 Agent 中间件。"""

from datetime import UTC, datetime
from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import ToolMessage, messages_to_dict
from langgraph.config import get_config
from langgraph.runtime import Runtime
from sqlalchemy import JSON, Column
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool
from sqlmodel import Field, SQLModel, select

from deepclaw.web_backend.db import (
    build_async_sessionmaker,
    make_async_url,
    resolve_metadata_db_url,
)


def utc_now() -> datetime:
    """返回不带时区信息的当前 UTC 时间。

    Args:
        无。
    """
    return datetime.now(UTC).replace(tzinfo=None)


class ThreadMessages(SQLModel, table=True):
    """一个线程对应一条完整 messages 记录。"""

    __tablename__ = "thread_messages"

    thread_id: str = Field(primary_key=True)
    messages: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class ThreadMessageStore:
    """直接读写 thread_messages 表的异步存储。"""

    def __init__(self, db_url: str | None = None):
        """初始化线程消息表的异步数据库连接。

        Args:
            db_url: 可选数据库连接串；未提供时使用项目元数据数据库。
        """
        self.db_url = db_url or resolve_metadata_db_url("thread_messages.db")
        connect_args = {"check_same_thread": False} if self.db_url.startswith("sqlite") else {}
        self.engine = create_async_engine(
            make_async_url(self.db_url),
            connect_args=connect_args,
            poolclass=NullPool,
        )
        self.async_session = build_async_sessionmaker(self.engine)
        self._initialized = False

    async def _ensure_initialized(self) -> None:
        """创建 thread_messages 表。

        Args:
            无。
        """
        if self._initialized:
            return
        async with self.engine.begin() as connection:
            await connection.run_sync(ThreadMessages.__table__.create, checkfirst=True)
        self._initialized = True

    async def save_messages(
        self,
        thread_id: str,
        messages: list[dict[str, Any]],
    ) -> ThreadMessages:
        """按线程覆盖保存完整消息列表。

        Args:
            thread_id: LangGraph 线程 ID。
            messages: 已序列化的完整消息列表。
        """
        await self._ensure_initialized()
        async with self.async_session() as session:
            result = await session.exec(
                select(ThreadMessages).where(ThreadMessages.thread_id == thread_id)
            )
            record = result.first()
            if record is not None and record.messages == messages:
                return record

            now = utc_now()
            if record is None:
                record = ThreadMessages(
                    thread_id=thread_id,
                    messages=messages,
                    created_at=now,
                    updated_at=now,
                )
            else:
                record.messages = messages
                record.updated_at = now

            session.add(record)
            await session.commit()
            await session.refresh(record)
            return record

    async def get_messages(self, thread_id: str) -> ThreadMessages | None:
        """读取指定线程保存的消息记录。

        Args:
            thread_id: LangGraph 线程 ID。
        """
        await self._ensure_initialized()
        async with self.async_session() as session:
            result = await session.exec(
                select(ThreadMessages).where(ThreadMessages.thread_id == thread_id)
            )
            return result.first()

    async def close(self) -> None:
        """释放数据库连接池。

        Args:
            无。
        """
        await self.engine.dispose()


_thread_message_store: ThreadMessageStore | None = None


def get_thread_message_store() -> ThreadMessageStore:
    """获取线程消息表的单例存储对象。

    Args:
        无。
    """
    global _thread_message_store
    if _thread_message_store is None:
        _thread_message_store = ThreadMessageStore()
    return _thread_message_store


class MessageStoreMiddleware(AgentMiddleware):
    """在 Agent 运行过程内持续将完整 messages 写入自建表。"""

    def __init__(self, message_store: ThreadMessageStore | None = None):
        """初始化消息存储中间件。

        Args:
            message_store: 可选线程消息存储；未提供时使用单例存储。
        """
        self.message_store = message_store or get_thread_message_store()

    async def aafter_agent(
        self,
        state: dict[str, Any],
        runtime: Runtime[Any],
    ) -> None:
        """在 Agent 正常结束后保存最终消息列表。

        Args:
            state: 当前 Agent 的最终状态。
            runtime: 当前运行时对象。
        """
        await self._save_state_messages(state)
        return None

    async def abefore_agent(
        self,
        state: dict[str, Any],
        runtime: Runtime[Any],
    ) -> None:
        """在 Agent 开始时保存已接收的用户消息。

        Args:
            state: 当前 Agent 的初始状态。
            runtime: 当前运行时对象。
        """
        await self._save_state_messages(state)
        return None

    async def aafter_model(
        self,
        state: dict[str, Any],
        runtime: Runtime[Any],
    ) -> None:
        """在每次模型调用后保存最新消息状态。

        Args:
            state: 当前模型调用后的 Agent 状态。
            runtime: 当前运行时对象。
        """
        await self._save_state_messages(state)
        return None

    async def abefore_model(
        self,
        state: dict[str, Any],
        runtime: Runtime[Any],
    ) -> None:
        """在每次模型调用前保存经过中间件处理的消息状态。

        Args:
            state: 当前模型调用前的 Agent 状态。
            runtime: 当前运行时对象。
        """
        await self._save_state_messages(state)
        return None

    async def awrap_tool_call(self, request, handler):
        """在工具执行完成后立即保存工具结果。

        Args:
            request: 当前工具调用请求。
            handler: 执行实际工具调用的异步处理器。
        """
        response = await handler(request)
        messages = list(request.state.get("messages", []))
        if isinstance(response, ToolMessage):
            messages.append(response)
        elif isinstance(getattr(response, "update", None), dict):
            messages = response.update.get("messages", messages)
        await self._save_messages(messages)
        return response

    async def _save_state_messages(self, state: dict[str, Any]) -> None:
        """保存状态中包含的 messages。

        Args:
            state: 含有 messages 的 Agent 状态。
        """
        await self._save_messages(state.get("messages"))

    async def _save_messages(self, messages: list[Any] | None) -> None:
        """使用当前运行线程 ID 覆盖保存消息列表。

        Args:
            messages: 待保存的完整消息列表。
        """
        thread_id = get_config().get("configurable", {}).get("thread_id")
        if not isinstance(thread_id, str) or not messages:
            return None

        await self.message_store.save_messages(thread_id, messages_to_dict(messages))
        return None
