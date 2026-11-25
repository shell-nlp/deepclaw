"""聊天文件的归属、元数据与对象存储。"""

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import PurePosixPath
from uuid import uuid4
from zipfile import BadZipFile

from lxml.etree import XMLSyntaxError
from openpyxl.utils.exceptions import InvalidFileException
from sqlalchemy import DateTime, delete, func, inspect, text, update
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlmodel import Field, SQLModel, select

from deepclaw.common.object_storage import create_object_storage
from deepclaw.common.object_storage.base import ObjectStorage
from deepclaw.middleware.files.formats import extract_document
from deepclaw.settings import settings
from deepclaw.utils.db import build_async_sessionmaker, create_async_engine_from_url
from deepclaw.web_backend.db import resolve_metadata_db_url

BUCKET = "chat-files"
MAX_BYTES = 20 * 1024 * 1024
MIME_TYPES = {
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}
logger = logging.getLogger(__name__)


class ChatFile(SQLModel, table=True):
    """当前账号的不可变文件记录。"""

    __tablename__ = "chat_files"
    id: str = Field(primary_key=True, max_length=32)
    owner: str = Field(index=True, max_length=128)
    name: str = Field(max_length=255)
    extension: str = Field(max_length=8)
    size: int
    created_at: datetime = Field(sa_type=DateTime)
    favorite: bool = Field(default=False)
    returned_at: datetime | None = Field(default=None, sa_type=DateTime)
    deleting: bool = Field(default=False)


class FileRetention(SQLModel, table=True):
    """账号的自动清理规则。"""

    __tablename__ = "chat_file_retention"
    owner: str = Field(primary_key=True, max_length=128)
    retention_days: int | None = None


def utc_now() -> datetime:
    """返回供数据库存储的无时区 UTC 时间。

    Args:
        无。
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _ensure_tables(connection) -> None:
    """创建文件表并为已有文件记录补齐收藏和清理状态。

    Args:
        connection: 已持有初始化锁的数据库连接。
    """
    ChatFile.__table__.create(connection, checkfirst=True)
    FileRetention.__table__.create(connection, checkfirst=True)
    columns = {column["name"] for column in inspect(connection).get_columns("chat_files")}
    for name, definition in (
        ("favorite", "BOOLEAN NOT NULL DEFAULT FALSE"),
        ("returned_at", "TIMESTAMP"),
        ("deleting", "BOOLEAN NOT NULL DEFAULT FALSE"),
    ):
        if name not in columns:
            connection.exec_driver_sql(f"ALTER TABLE chat_files ADD COLUMN {name} {definition}")


def file_details(record: ChatFile) -> dict:
    """构造可返回给客户端或模型的文件信息。

    Args:
        record: 已授权的文件记录。
    """
    return {
        "file_id": record.id,
        "name": record.name,
        "extension": record.extension,
        "size": record.size,
        "created_at": record.created_at.isoformat() + "Z",
        "favorite": record.favorite,
        "download_url": f"/api/files/{record.id}/download",
    }


class FileService:
    """在对象存储和业务数据库中保存归属明确的文件。"""

    def __init__(self, db_url: str, storage: ObjectStorage):
        """创建文件服务。

        Args:
            db_url: 统一元数据库地址。
            storage: 对象存储实例。
        """
        self.engine = create_async_engine_from_url(db_url)
        self.sessions = build_async_sessionmaker(self.engine)
        self.storage = storage
        self._lock = asyncio.Lock()
        self._initialized = False

    async def initialize(self):
        """初始化本模块的元数据表。

        Args:
            无。
        """
        if self._initialized:
            return
        async with self._lock:
            if self._initialized:
                return
            async with self.engine.begin() as connection:
                if connection.dialect.name == "postgresql":
                    await connection.execute(text("SELECT pg_advisory_xact_lock(44587231)"))
                elif connection.dialect.name == "sqlite":
                    await connection.exec_driver_sql("BEGIN IMMEDIATE")
                await connection.run_sync(_ensure_tables)
            self._initialized = True

    async def save(self, owner: str, name: str, data: bytes) -> ChatFile:
        """解析和保存文件原件及其行索引。

        Args:
            owner: 可信账号 ID。
            name: 上传或生成的文件名。
            data: 原件字节。
        """
        name = PurePosixPath(name.replace("\\", "/")).name.strip()
        extension = PurePosixPath(name).suffix.lower()
        if extension not in MIME_TYPES or len(name) > 255 or any(ord(char) < 32 for char in name):
            raise ValueError("文件名无效或格式不受支持。")
        if len(data) > MAX_BYTES:
            raise ValueError("文件大小不能超过 20 MiB。")
        try:
            parsed = await asyncio.to_thread(extract_document, extension, data)
        except ValueError:
            raise
        except (BadZipFile, InvalidFileException, XMLSyntaxError, KeyError, OSError, RuntimeError) as exc:
            raise ValueError("无法解析文件，请检查文件是否损坏或加密。") from exc

        await self.initialize()
        record = ChatFile(
            id=uuid4().hex, owner=owner, name=name, extension=extension,
            size=len(data), created_at=utc_now(),
        )
        original_key = f"{record.id}/original{extension}"
        parsed_key = f"{record.id}/parsed-v1.json"
        try:
            cache = await asyncio.to_thread(lambda: json.dumps(parsed, ensure_ascii=False).encode())
            await asyncio.to_thread(self.storage.put_bytes, BUCKET, original_key, data, MIME_TYPES[extension])
            await asyncio.to_thread(self.storage.put_bytes, BUCKET, parsed_key, cache, "application/json")
            async with self.sessions() as session:
                session.add(record)
                await session.commit()
        except Exception:
            for key in (original_key, parsed_key):
                try:
                    await asyncio.to_thread(self.storage.delete_object, BUCKET, key)
                except Exception:
                    logger.exception("清理未保存的文件对象失败")
            raise
        return record

    async def get(self, owner: str, file_id: str) -> ChatFile:
        """查找当前账号可访问的文件。

        Args:
            owner: 可信账号 ID。
            file_id: 文件 ID。
        """
        await self.initialize()
        async with self.sessions() as session:
            result = await session.exec(select(ChatFile).where(
                ChatFile.id == file_id, ChatFile.owner == owner, ChatFile.deleting.is_(False),
            ))
            record = result.one_or_none()
        if record is None:
            raise LookupError("找不到文件。")
        return record

    async def list(self, owner: str, offset: int, limit: int, favorite: bool | None = None) -> list[ChatFile]:
        """按创建时间分页列出当前账号的文件。

        Args:
            owner: 可信账号 ID。
            offset: 跳过的文件数。
            limit: 返回数量。
            favorite: 按收藏状态筛选，省略时返回两区。
        """
        await self.initialize()
        async with self.sessions() as session:
            query = select(ChatFile).where(ChatFile.owner == owner, ChatFile.deleting.is_(False))
            if favorite is not None:
                query = query.where(ChatFile.favorite.is_(favorite))
            result = await session.exec(query.order_by(
                func.coalesce(ChatFile.returned_at, ChatFile.created_at).desc(), ChatFile.id.desc(),
            ).offset(offset).limit(limit))
            return list(result.all())

    async def set_favorite(self, owner: str, file_id: str, favorite: bool) -> ChatFile:
        """移动文件归属，取消收藏时重新计算保留期。

        Args:
            owner: 可信账号 ID。
            file_id: 文件 ID。
            favorite: 目标收藏状态。
        """
        await self.initialize()
        values = {"favorite": favorite}
        if not favorite:
            values["returned_at"] = utc_now()
        async with self.sessions() as session:
            await session.exec(update(ChatFile).where(
                ChatFile.id == file_id, ChatFile.owner == owner,
                ChatFile.deleting.is_(False), ChatFile.favorite.is_(not favorite),
            ).values(**values))
            await session.commit()
        return await self.get(owner, file_id)

    async def get_retention(self, owner: str) -> int | None:
        """读取账号的保留天数。

        Args:
            owner: 可信账号 ID。
        """
        await self.initialize()
        async with self.sessions() as session:
            policy = await session.get(FileRetention, owner)
            return policy.retention_days if policy else None

    async def set_retention(self, owner: str, days: int | None) -> None:
        """保存账号的自动清理设置。

        Args:
            owner: 可信账号 ID。
            days: 保留天数，为空表示关闭。
        """
        await self.initialize()
        insert = postgres_insert if self.engine.dialect.name == "postgresql" else sqlite_insert
        async with self.sessions() as session:
            await session.exec(insert(FileRetention).values(owner=owner, retention_days=days).on_conflict_do_update(
                index_elements=["owner"], set_={"retention_days": days},
            ))
            await session.commit()

    async def clean_expired(self, now: datetime) -> None:
        """认领到期文件，清除原件和解析缓存。

        Args:
            now: 本轮清理使用的无时区 UTC 时间。
        """
        await self.initialize()
        async with self.sessions() as session:
            policies = (await session.exec(select(FileRetention).where(
                FileRetention.retention_days.is_not(None),
            ))).all()
            for policy in policies:
                cutoff = now - timedelta(days=policy.retention_days)
                eligible = (
                    ChatFile.owner == policy.owner, ChatFile.favorite.is_(False),
                    ChatFile.deleting.is_(False),
                    func.coalesce(ChatFile.returned_at, ChatFile.created_at) <= cutoff,
                )
                batch = select(ChatFile.id).where(*eligible).order_by(ChatFile.created_at, ChatFile.id).limit(250)
                policy_still_applies = select(FileRetention.owner).where(
                    FileRetention.owner == policy.owner,
                    FileRetention.retention_days == policy.retention_days,
                ).exists()
                await session.exec(update(ChatFile).where(
                    ChatFile.id.in_(batch), *eligible, policy_still_applies,
                ).values(deleting=True))
            await session.commit()
            pending = (await session.exec(select(ChatFile).where(ChatFile.deleting.is_(True)))).all()
        for record in pending:
            try:
                await asyncio.to_thread(self.storage.delete_object, BUCKET, f"{record.id}/original{record.extension}")
                await asyncio.to_thread(self.storage.delete_object, BUCKET, f"{record.id}/parsed-v1.json")
            except Exception:
                logger.exception("清理过期文件失败，稍后重试，文件 ID %s", record.id)
                continue
            async with self.sessions() as session:
                await session.exec(delete(ChatFile).where(ChatFile.id == record.id, ChatFile.deleting.is_(True)))
                await session.commit()

    async def parsed(self, record: ChatFile) -> dict:
        """读取已授权文件的解析结果。

        Args:
            record: 已授权的文件记录。
        """
        data = await asyncio.to_thread(self.storage.get_bytes, BUCKET, f"{record.id}/parsed-v1.json")
        return await asyncio.to_thread(json.loads, data)

    async def download(self, record: ChatFile) -> bytes:
        """读取已授权文件的原件字节。

        Args:
            record: 已授权的文件记录。
        """
        key = f"{record.id}/original{record.extension}"
        return await asyncio.to_thread(self.storage.get_bytes, BUCKET, key)


@lru_cache(maxsize=1)
def get_file_service() -> FileService:
    """按运行配置创建进程内文件服务。

    Args:
        无。
    """
    return FileService(resolve_metadata_db_url(), create_object_storage(settings))


async def close_file_service() -> None:
    """释放已创建的文件数据库连接。

    Args:
        无。
    """
    if get_file_service.cache_info().currsize:
        await get_file_service().engine.dispose()
        get_file_service.cache_clear()


async def file_retention_worker() -> None:
    """定期清理到期的未收藏文件，失败后保留记录供下次重试。

    Args:
        无。
    """
    while True:
        try:
            await get_file_service().clean_expired(utc_now())
        except Exception:
            logger.exception("文件自动清理执行失败")
        await asyncio.sleep(3600)
