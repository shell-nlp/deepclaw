import asyncio
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from uuid import uuid4
from zoneinfo import ZoneInfo

from croniter import CroniterBadDateError, croniter
from sqlalchemy import Column, DateTime, Index, JSON, Text, func, update
from sqlmodel import Field, SQLModel, select

from deepclaw.middleware.cron.schemas import NotificationsResponse, ScheduleRequest, ScheduleResponse, ScheduleRunResponse
from deepclaw.utils.db import build_async_sessionmaker, create_async_engine_from_url
from deepclaw.web_backend.db import resolve_metadata_db_url

RUN_TIMEOUT = timedelta(minutes=5)


def utc_now() -> datetime:
    """返回数据库使用的无时区 UTC 时间。

    Args:
        无。
    """
    return datetime.now(UTC).replace(tzinfo=None)


def next_occurrence(settings: ScheduleRequest, after: datetime) -> datetime:
    """解析严格晚于基准时间的触发时间，返回无时区 UTC。

    Args:
        settings: 定时任务设置。
        after: 无时区 UTC 基准。
    """
    if settings.run_at is not None:
        return settings.run_at.astimezone(UTC).replace(tzinfo=None)
    if settings.interval_seconds is not None:
        try:
            return after + timedelta(seconds=settings.interval_seconds)
        except OverflowError as exc:
            raise ValueError("执行间隔过长。") from exc
    local_time = after.replace(tzinfo=UTC).astimezone(ZoneInfo(settings.timezone))
    try:
        result = croniter(settings.cron, local_time, second_at_beginning=True).get_next(datetime)
    except CroniterBadDateError as exc:
        raise ValueError("该 Cron 表达式没有可执行的日期。") from exc
    return result.astimezone(UTC).replace(tzinfo=None)


class ScheduledTask(SQLModel, table=True):
    __tablename__ = "scheduled_tasks"
    __table_args__ = (Index("ix_scheduled_tasks_due", "next_at", "lease_until"),)

    id: str = Field(default_factory=lambda: uuid4().hex, primary_key=True)
    owner: str = Field(index=True)
    settings: dict = Field(sa_column=Column(JSON, nullable=False))
    next_at: datetime | None = Field(default=None, sa_type=DateTime)
    lease_until: datetime | None = Field(default=None, sa_type=DateTime)
    revision: str = Field(default_factory=lambda: uuid4().hex)


class ScheduledRun(SQLModel, table=True):
    __tablename__ = "scheduled_task_runs"
    __table_args__ = (
        Index("ix_scheduled_runs_owner_finished", "owner", "finished_at"),
        Index("ix_scheduled_runs_status_lease", "status", "lease_until"),
    )

    id: str = Field(default_factory=lambda: uuid4().hex, primary_key=True)
    job_id: str = Field(index=True)
    owner: str
    name: str
    status: str = "running"
    scheduled_at: datetime = Field(sa_type=DateTime)
    lease_until: datetime = Field(sa_type=DateTime)
    finished_at: datetime | None = Field(default=None, sa_type=DateTime)
    read_at: datetime | None = Field(default=None, sa_type=DateTime)
    message: str | None = Field(default=None, sa_type=Text)
    filename: str | None = None

    def response(self) -> ScheduleRunResponse:
        """转换为带 UTC 时区且省略内部字段的运行结果。

        Args:
            无。
        """
        return ScheduleRunResponse(
            id=self.id, job_id=self.job_id, name=self.name, status=self.status,
            scheduled_at=self.scheduled_at.replace(tzinfo=UTC),
            finished_at=self.finished_at.replace(tzinfo=UTC) if self.finished_at else None,
            read_at=self.read_at.replace(tzinfo=UTC) if self.read_at else None,
            message=self.message, filename=self.filename,
        )


class ScheduleStore:
    def __init__(self, db_url: str):
        """创建定时任务存储。

        Args:
            db_url: 元数据数据库地址。
        """
        self.engine = create_async_engine_from_url(db_url)
        self.sessions = build_async_sessionmaker(self.engine)
        self.initialized = False
        self.init_lock = asyncio.Lock()

    async def initialize(self):
        """创建定时任务和运行结果表。

        Args:
            无。
        """
        async with self.init_lock:
            if self.initialized:
                return
            async with self.engine.begin() as connection:
                dialect = connection.dialect.name
                if dialect == "postgresql":
                    from sqlalchemy import text

                    await connection.execute(text("SELECT pg_advisory_xact_lock(42760712)"))
                elif dialect == "sqlite":
                    await connection.exec_driver_sql("BEGIN IMMEDIATE")
                await connection.run_sync(
                    SQLModel.metadata.create_all,
                    tables=[ScheduledTask.__table__, ScheduledRun.__table__],
                )
            self.initialized = True

    async def list_jobs(self, owner: str) -> list[ScheduleResponse]:
        """列出当前账号的任务。

        Args:
            owner: 登录账号 ID。
        """
        await self.initialize()
        async with self.sessions() as session:
            jobs = (await session.exec(
                select(ScheduledTask).where(ScheduledTask.owner == owner)
                .order_by(ScheduledTask.next_at.asc().nulls_last(), ScheduledTask.id)
            )).all()
            return [self.response(job) for job in jobs]

    @staticmethod
    def response(job: ScheduledTask) -> ScheduleResponse:
        """转换为对外任务数据。

        Args:
            job: 已保存的任务。
        """
        return ScheduleResponse(
            id=job.id, settings=ScheduleRequest.model_validate(job.settings),
            next_at=job.next_at.replace(tzinfo=UTC) if job.next_at else None,
        )

    async def save(self, owner: str, settings: ScheduleRequest, job_id: str | None = None) -> ScheduleResponse:
        """新建或替换当前账号的任务配置。

        Args:
            owner: 登录账号 ID。
            settings: 提交的任务配置。
            job_id: 编辑时填写任务 ID。
        """
        await self.initialize()
        now = utc_now()
        async with self.sessions() as session:
            job = ScheduledTask(owner=owner, settings={})
            if job_id is not None:
                job = (await session.exec(select(ScheduledTask).where(
                    ScheduledTask.id == job_id, ScheduledTask.owner == owner
                ).with_for_update())).first()
                if job is None:
                    raise LookupError("找不到定时任务。")
            next_at = next_occurrence(settings, now)
            saved = settings.model_dump(mode="json")
            if settings.run_at is not None and next_at <= now and settings.enabled:
                previous = job.settings
                if not previous.get("enabled") or previous.get("run_at") != saved["run_at"]:
                    raise ValueError("一次性任务的执行时间必须晚于当前时间。")
                next_at = job.next_at
            job.settings = saved
            job.next_at = next_at if settings.enabled else None
            job.revision = uuid4().hex
            session.add(job)
            await session.commit()
            await session.refresh(job)
            return self.response(job)

    async def remove(self, owner: str, job_id: str) -> None:
        """删除任务配置并保留已产生的结果。

        Args:
            owner: 登录账号 ID。
            job_id: 任务 ID。
        """
        await self.initialize()
        async with self.sessions() as session:
            job = (await session.exec(select(ScheduledTask).where(
                ScheduledTask.id == job_id, ScheduledTask.owner == owner
            ).with_for_update())).first()
            if job is None:
                raise LookupError("找不到定时任务。")
            await session.delete(job)
            await session.commit()

    async def set_enabled(self, owner: str, job_id: str, enabled: bool) -> ScheduleResponse:
        """更新任务的启停状态，并保留正在执行任务的租约。

        Args:
            owner: 登录账号 ID。
            job_id: 任务 ID。
            enabled: 是否允许后续调度。
        """
        await self.initialize()
        async with self.sessions() as session:
            job = (await session.exec(select(ScheduledTask).where(
                ScheduledTask.id == job_id, ScheduledTask.owner == owner,
            ).with_for_update())).first()
            if job is None:
                raise LookupError("找不到定时任务。")
            settings = ScheduleRequest.model_validate(job.settings)
            if settings.enabled == enabled:
                return self.response(job)
            now = utc_now()
            next_at = next_occurrence(settings, now) if enabled else None
            if enabled and next_at <= now:
                raise ValueError("请先将一次性任务的执行时间改为将来的时间。")
            settings.enabled = enabled
            job.settings = settings.model_dump(mode="json")
            job.next_at = next_at
            job.revision = uuid4().hex
            session.add(job)
            await session.commit()
            await session.refresh(job)
            return self.response(job)

    async def claim(self) -> tuple[ScheduledRun, ScheduleRequest] | None:
        """原子领取一个到期任务，同时登记运行和推进调度。

        Args:
            无。
        """
        await self.initialize()
        now = utc_now()
        async with self.sessions() as session:
            job = (await session.exec(select(ScheduledTask).where(
                ScheduledTask.next_at <= now,
                (ScheduledTask.lease_until == None) | (ScheduledTask.lease_until <= now),
            ).order_by(ScheduledTask.next_at, ScheduledTask.id).limit(1))).first()
            if job is None:
                return None
            settings = ScheduleRequest.model_validate(job.settings)
            deadline = now + RUN_TIMEOUT + timedelta(seconds=15)
            scheduled_at = job.next_at
            following = None
            if settings.interval_seconds is not None:
                interval = timedelta(seconds=settings.interval_seconds)
                following = now + interval - (now - scheduled_at) % interval
            elif settings.cron is not None:
                following = next_occurrence(settings, now)
            claimed = await session.exec(update(ScheduledTask).where(
                ScheduledTask.id == job.id, ScheduledTask.revision == job.revision,
            ).values(next_at=following, lease_until=deadline, revision=uuid4().hex)
                .returning(ScheduledTask.id))
            if claimed.first() is None:
                return None
            run = ScheduledRun(
                owner=job.owner, job_id=job.id, name=settings.name,
                scheduled_at=scheduled_at, lease_until=deadline,
            )
            session.add(run)
            await session.commit()
            await session.refresh(run)
            return run, settings

    async def expire_runs(self) -> None:
        """将失去执行进程的运行标为失败。

        Args:
            无。
        """
        await self.initialize()
        now = utc_now()
        async with self.sessions() as session:
            await session.exec(update(ScheduledRun).where(
                ScheduledRun.status == "running", ScheduledRun.lease_until <= now,
            ).values(status="failed", finished_at=now, message="任务执行中断。"))
            await session.commit()

    async def finish(self, run: ScheduledRun, *, status: str, message: str, filename: str | None = None):
        """持久化结果并释放对应任务的执行租约。

        Args:
            run: 已领取的运行。
            status: 成功或失败状态。
            message: 通知正文或失败原因。
            filename: 可下载文件名称。
        """
        async with self.sessions() as session:
            finished = await session.exec(update(ScheduledRun).where(
                ScheduledRun.id == run.id, ScheduledRun.status == "running",
                ScheduledRun.lease_until > utc_now(),
            ).values(status=status, message=message, filename=filename, finished_at=utc_now())
                .returning(ScheduledRun.id))
            if finished.first() is None:
                return False
            await session.exec(update(ScheduledTask).where(
                ScheduledTask.id == run.job_id, ScheduledTask.lease_until == run.lease_until,
            ).values(lease_until=None))
            await session.commit()
            return True

    async def notifications(self, owner: str, before: str | None = None) -> NotificationsResponse:
        """读取当前账号最近的执行结果及未读数量。

        Args:
            owner: 登录账号 ID。
            before: 分页游标，当前保留全部历史。
        """
        await self.initialize()
        async with self.sessions() as session:
            scope = (ScheduledRun.owner == owner, ScheduledRun.finished_at.is_not(None))
            query = select(ScheduledRun).where(*scope)
            if before is not None:
                cursor = (await session.exec(select(ScheduledRun).where(
                    *scope, ScheduledRun.id == before
                ))).first()
                if cursor is None:
                    query = query.where(ScheduledRun.id == "")
                else:
                    query = query.where(
                        (ScheduledRun.finished_at < cursor.finished_at)
                        | ((ScheduledRun.finished_at == cursor.finished_at) & (ScheduledRun.id < cursor.id))
                    )
            results = (await session.exec(query
                .order_by(ScheduledRun.finished_at.desc(), ScheduledRun.id.desc()).limit(50)
            )).all()
            unread = (await session.exec(select(func.count()).select_from(ScheduledRun)
                .where(*scope, ScheduledRun.read_at.is_(None)))).one()
            return NotificationsResponse(items=[row.response() for row in results], unread=unread)

    async def mark_read(self, owner: str, run_ids: list[str]) -> None:
        """标记当前账号指定的通知为已读。

        Args:
            owner: 登录账号 ID。
            run_ids: 用户已查看的运行 ID。
        """
        await self.initialize()
        async with self.sessions() as session:
            await session.exec(update(ScheduledRun).where(
                ScheduledRun.owner == owner, ScheduledRun.id.in_(run_ids),
                ScheduledRun.finished_at.is_not(None), ScheduledRun.read_at.is_(None),
            ).values(read_at=utc_now()))
            await session.commit()

    async def artifact(self, owner: str, run_id: str) -> ScheduledRun | None:
        """查找当前账号对应的可下载结果。

        Args:
            owner: 登录账号 ID。
            run_id: 运行 ID。
        """
        await self.initialize()
        async with self.sessions() as session:
            return (await session.exec(select(ScheduledRun).where(
                ScheduledRun.owner == owner, ScheduledRun.id == run_id,
                ScheduledRun.status == "succeeded", ScheduledRun.filename.is_not(None),
            ))).first()

    async def delete_notification(self, owner: str, run_id: str) -> None:
        """删除当前账号的一条已完成通知。

        Args:
            owner: 登录账号 ID。
            run_id: 任务执行 ID。
        """
        await self.initialize()
        async with self.sessions() as session:
            run = (await session.exec(select(ScheduledRun).where(
                ScheduledRun.owner == owner, ScheduledRun.id == run_id,
                ScheduledRun.finished_at.is_not(None),
            ))).first()
            if run is None:
                raise LookupError("找不到任务通知。")
            await session.delete(run)
            await session.commit()


@lru_cache(maxsize=1)
def get_schedule_store() -> ScheduleStore:
    """获取当前服务的定时任务存储。

    Args:
        无。
    """
    return ScheduleStore(resolve_metadata_db_url())

