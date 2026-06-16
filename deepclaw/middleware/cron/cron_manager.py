import os
from datetime import datetime
from typing import Optional

from sqlmodel import select
from sqlmodel import Field, SQLModel

from deepclaw.constant import home_path
from deepclaw.web_backend.db import build_async_sessionmaker, create_async_engine_from_url


class CronJob(SQLModel, table=True):
    __tablename__ = "cron_jobs"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True, unique=True)
    cron_expression: str
    command: str
    description: Optional[str] = None
    enabled: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class CronManager:
    def __init__(self, db_url: Optional[str] = None):
        if db_url is None:
            os.makedirs(home_path, exist_ok=True)
            db_url = f"sqlite:///{os.path.join(home_path, 'cron.db')}"

        self.engine = create_async_engine_from_url(db_url)
        self.async_session = build_async_sessionmaker(self.engine)
        self._init_done = False

    async def _ensure_init(self):
        if self._init_done:
            return
        async with self.engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.create_all)
        self._init_done = True

    async def add(
        self,
        name: str,
        cron_expression: str,
        command: str,
        description: Optional[str] = None,
    ) -> CronJob:
        await self._ensure_init()
        async with self.async_session() as session:
            job = CronJob(
                name=name,
                cron_expression=cron_expression,
                command=command,
                description=description,
            )
            session.add(job)
            await session.commit()
            await session.refresh(job)
            return job

    async def list(self, enabled: Optional[bool] = None) -> list[CronJob]:
        await self._ensure_init()
        async with self.async_session() as session:
            statement = select(CronJob)
            if enabled is not None:
                statement = statement.where(CronJob.enabled == enabled)
            statement = statement.order_by(CronJob.created_at.desc())
            result = await session.exec(statement)
            return list(result.all())

    async def get(
        self,
        job_id: Optional[int] = None,
        name: Optional[str] = None,
    ) -> Optional[CronJob]:
        await self._ensure_init()
        async with self.async_session() as session:
            if job_id is not None:
                return await session.get(CronJob, job_id)
            if name:
                result = await session.exec(
                    select(CronJob).where(CronJob.name == name)
                )
                return result.first()
        return None

    async def remove(self, job_id: Optional[int] = None, name: Optional[str] = None) -> bool:
        await self._ensure_init()
        async with self.async_session() as session:
            if job_id is not None:
                job = await session.get(CronJob, job_id)
            elif name:
                result = await session.exec(
                    select(CronJob).where(CronJob.name == name)
                )
                job = result.first()
            else:
                return False

            if job is None:
                return False

            await session.delete(job)
            await session.commit()
            return True

    async def update(
        self,
        job_id: Optional[int] = None,
        name: Optional[str] = None,
        **kwargs,
    ) -> Optional[CronJob]:
        await self._ensure_init()
        async with self.async_session() as session:
            if job_id is not None:
                job = await session.get(CronJob, job_id)
            elif name:
                result = await session.exec(
                    select(CronJob).where(CronJob.name == name)
                )
                job = result.first()
            else:
                return None

            if job is None:
                return None

            for key, value in kwargs.items():
                if hasattr(job, key) and value is not None:
                    setattr(job, key, value)

            job.updated_at = datetime.utcnow()
            session.add(job)
            await session.commit()
            await session.refresh(job)
            return job


_manager: Optional[CronManager] = None


def get_cron_manager(db_url: Optional[str] = None) -> CronManager:
    global _manager
    if _manager is None or db_url is not None:
        _manager = CronManager(db_url)
    return _manager
