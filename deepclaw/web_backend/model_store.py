"""统一数据库中的模型目录及一次性旧配置导入。"""

import asyncio
from functools import lru_cache
from typing import Any

from sqlalchemy import JSON, text, update
from sqlmodel import Field, SQLModel, select

from deepclaw.model_config import apply_active_model_config, load_initial_model_state, remove_imported_model_file
from deepclaw.utils.db import build_async_sessionmaker, create_async_engine_from_url
from deepclaw.web_backend.db import resolve_metadata_db_url


class ModelCatalog(SQLModel, table=True):
    """单行保存模型目录及默认模型指针，以便一起提交。"""

    __tablename__ = "model_catalog"
    id: int = Field(default=1, primary_key=True)
    revision: int = Field(default=1)
    configuration: dict[str, Any] = Field(sa_type=JSON)


class ModelCatalogChangedError(Exception):
    """目录已被另一个请求修改。"""


class ModelCatalogStore:
    """读写共享的模型目录。"""

    def __init__(self, db_url: str):
        """创建异步数据库连接。

        Args:
            db_url: 统一元数据数据库的连接地址。
        """
        self.engine = create_async_engine_from_url(db_url)
        self.sessions = build_async_sessionmaker(self.engine)
        self.revision = 0
        self._initialized = False
        self._lock = asyncio.Lock()

    async def initialize(self) -> None:
        """建表并在首次启动时导入已有模型。

        Args:
            无。
        """
        async with self._lock:
            if self._initialized:
                return
            async with self.sessions() as session:
                connection = await session.connection()
                if connection.dialect.name == "sqlite":
                    await session.exec(text("BEGIN IMMEDIATE"))
                else:
                    await session.exec(text("SELECT pg_advisory_xact_lock(1938317041)"))
                await connection.run_sync(ModelCatalog.__table__.create, checkfirst=True)
                row = (await session.exec(select(ModelCatalog).where(ModelCatalog.id == 1))).first()
                if row is None:
                    row = ModelCatalog(configuration=await asyncio.to_thread(load_initial_model_state))
                    session.add(row)
                await session.commit()
                await asyncio.to_thread(remove_imported_model_file, row.configuration.get("legacy_import_sha256"))
                apply_active_model_config(row.configuration)
                self.revision = row.revision
                self._initialized = True

    async def load(self) -> dict[str, Any]:
        """读取模型目录及其并发控制版本。

        Args:
            无。
        """
        await self.initialize()
        async with self.sessions() as session:
            row = (await session.exec(select(ModelCatalog).where(ModelCatalog.id == 1))).one()
            return {**row.configuration, "revision": row.revision}

    async def refresh(self) -> bool:
        """同步其他进程提交的活动模型配置。

        Args:
            无。
        """
        async with self.sessions() as session:
            row = (await session.exec(
                select(ModelCatalog).where(ModelCatalog.id == 1, ModelCatalog.revision > self.revision)
            )).first()
        if row is None or row.revision <= self.revision:
            return False
        apply_active_model_config(row.configuration)
        self.revision = row.revision
        return True

    async def save(self, state: dict[str, Any]) -> None:
        """保存目录，避免管理员的并发修改相互覆盖。

        Args:
            state: 带读取版本的目录状态。
        """
        revision = state["revision"]
        configuration = {key: value for key, value in state.items() if key != "revision"}
        async with self.sessions() as session:
            result = await session.exec(
                update(ModelCatalog)
                .where(ModelCatalog.id == 1, ModelCatalog.revision == revision)
                .values(configuration=configuration, revision=revision + 1)
            )
            if result.rowcount != 1:
                raise ModelCatalogChangedError
            await session.commit()
        if self.revision <= revision:
            apply_active_model_config(configuration)
            self.revision = revision + 1


@lru_cache(maxsize=1)
def get_model_catalog_store() -> ModelCatalogStore:
    """获取当前进程的模型目录存储。

    Args:
        无。
    """
    return ModelCatalogStore(resolve_metadata_db_url())


async def find_chat_model(model_id: str | None) -> dict[str, Any] | None:
    """读取指定聊天模型或当前默认模型。

    Args:
        model_id: 模型 ID，省略时使用数据库中的默认模型。
    """
    state = await get_model_catalog_store().load()
    selected_id = model_id or state.get("active_chat_model_id")
    return next(
        (model for model in state["models"] if model["id"] == selected_id and model.get("type") == "chat"),
        None,
    )
