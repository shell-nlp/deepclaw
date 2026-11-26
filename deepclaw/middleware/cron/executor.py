import asyncio
from io import BytesIO

from docx import Document
from langchain_core.messages import HumanMessage, SystemMessage
from loguru import logger

from deepclaw.common.object_storage import create_object_storage
from deepclaw.middleware.cron.schedule_store import RUN_TIMEOUT, ScheduleStore, ScheduledRun
from deepclaw.middleware.cron.schemas import ScheduleRequest
from deepclaw.middleware.files.service import get_file_service
from deepclaw.settings import settings
from deepclaw.utils import get_chat_model
from deepclaw.web_backend.auth.rbac.dependencies import agent_has_permission
from deepclaw.web_backend.auth.service import get_auth_service

BUCKET = "scheduled-task-results"
MAX_CONCURRENT_RUNS = 4
SCHEDULE_POLL_SECONDS = 1
ARTIFACT_RETRY_SECONDS = 300
MIME_TYPES = {
    "md": "text/markdown; charset=utf-8",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


def artifact_key(run: ScheduledRun, extension: str) -> str:
    """按账号、任务、执行批次构建产物对象键。

    Args:
        run: 任务执行记录。
        extension: 文件扩展名。
    """
    return f"{run.owner}/{run.job_id}/{run.id}.{extension}"


def render_artifact(content: str, extension: str) -> bytes:
    """将任务内容编码为 Markdown 或 Word 文件。

    Args:
        content: 文件正文。
        extension: 目标文件扩展名。
    """
    if extension == "md":
        return content.encode("utf-8")
    document = Document()
    for line in content.splitlines():
        document.add_paragraph(line)
    stream = BytesIO()
    document.save(stream)
    return stream.getvalue()


def write_artifact(run: ScheduledRun, extension: str, content: str) -> None:
    """生成文件并写到应用配置的对象存储。

    Args:
        run: 任务执行记录。
        extension: 文件扩展名。
        content: 文件正文。
    """
    create_object_storage(settings).put_bytes(
        BUCKET, artifact_key(run, extension), render_artifact(content, extension), MIME_TYPES[extension]
    )


async def publish_artifact(store: ScheduleStore, run: ScheduledRun) -> None:
    """把当前账号仍可下载的任务产物收录到文件知识库。

    Args:
        store: 与文件服务共用元数据库的定时任务存储。
        run: 执行记录，按其 ID 重新读取已完成的产物。
    """
    try:
        artifact = await store.artifact(run.owner, run.id)
        if artifact is None or artifact.file_registered:
            return
        if not await agent_has_permission(artifact.owner, "/api/files", "write"):
            return
        extension = artifact.filename.rsplit(".", 1)[-1]
        data = await asyncio.to_thread(
            create_object_storage(settings).get_bytes, BUCKET, artifact_key(artifact, extension),
        )
        await get_file_service().publish(
            artifact.owner, artifact.filename, data, created_at=artifact.finished_at,
            register=lambda record: store.register_artifact(artifact.id, record),
        )
    except FileNotFoundError:
        return
    except Exception as exc:
        logger.warning("定时任务文件收录失败 id={} type={}", run.id, type(exc).__name__)


async def backfill_artifacts(store: ScheduleStore) -> None:
    """分批补录已有任务文件，失败的产物由下一轮重试。

    Args:
        store: 定时任务存储。
    """
    after = ""
    while batch := await store.unpublished_artifacts(after):
        for run in batch:
            await publish_artifact(store, run)
        after = batch[-1].id


async def artifact_backfill_worker(store: ScheduleStore) -> None:
    """启动时补录历史文件，之后定期重试未收录的产物。

    Args:
        store: 定时任务存储。
    """
    while True:
        try:
            await backfill_artifacts(store)
        except Exception as exc:
            logger.warning("定时任务文件补录失败 type={}", type(exc).__name__)
        await asyncio.sleep(ARTIFACT_RETRY_SECONDS)


async def deliver(store: ScheduleStore, run: ScheduledRun, task: ScheduleRequest) -> None:
    """生成本次结果并完成投递。

    Args:
        store: 定时任务存储。
        run: 已领取的执行记录。
        task: 领取时保存的配置快照。
    """
    filename = None
    try:
        async with asyncio.timeout(RUN_TIMEOUT.total_seconds()):
            account = await get_auth_service().store.get_user_by_user_id(run.owner)
            if account is None or not account.is_active:
                await store.finish(run, status="failed", message="任务所属账号已停用或删除。")
                return
            content = task.content
            if task.mode == "generate":
                model = get_chat_model()
                output = await model.ainvoke([
                    SystemMessage(content=(
                        "你正在生成定时任务交付物。直接输出用户要求的正文。"
                        f"本次计划执行时间（UTC）：{run.response().scheduled_at.isoformat()}。"
                        + ("请输出纯文本，不带 Markdown 标记。" if task.output == "docx" else "")
                    )),
                    HumanMessage(content=content),
                ])
                content = output.text.strip()
                if not content:
                    raise ValueError("模型未返回正文")
            if task.output != "notification":
                await asyncio.to_thread(write_artifact, run, task.output, content)
                filename = f"{task.name}.{task.output}"
            finished = await store.finish(
                run, status="succeeded", filename=filename,
                message="文件已生成。" if filename else content,
            )
    except asyncio.CancelledError:
        await store.finish(run, status="failed", message="服务关闭，任务执行中断。")
        raise
    except Exception as exc:
        logger.warning("定时任务运行失败 id={} type={}", run.id, type(exc).__name__)
        message = "任务执行超时。" if isinstance(exc, TimeoutError) else "任务执行失败，请检查模型或对象存储配置。"
        await store.finish(run, status="failed", message=message)
    else:
        if finished and filename:
            await publish_artifact(store, run)


async def schedule_worker(store: ScheduleStore) -> None:
    """持续领取到期任务并回收过期执行记录。

    Args:
        store: 定时任务存储。
    """
    tasks: set[asyncio.Task] = set()
    backfill = asyncio.create_task(artifact_backfill_worker(store))
    next_expiration_check = 0.0
    loop = asyncio.get_running_loop()
    try:
        while True:
            finished = {task for task in tasks if task.done()}
            tasks.difference_update(finished)
            for task in finished:
                if not task.cancelled() and (error := task.exception()):
                    logger.warning("定时任务结果写入失败 type={}", type(error).__name__)
            try:
                if loop.time() >= next_expiration_check:
                    await store.expire_runs()
                    next_expiration_check = loop.time() + 30
                if len(tasks) < MAX_CONCURRENT_RUNS and (claimed := await store.claim()) is not None:
                    tasks.add(asyncio.create_task(deliver(store, *claimed)))
                    continue
            except Exception as exc:
                logger.warning("定时任务轮询失败 type={}", type(exc).__name__)
            if tasks:
                await asyncio.wait(tasks, timeout=SCHEDULE_POLL_SECONDS, return_when=asyncio.FIRST_COMPLETED)
            else:
                await asyncio.sleep(SCHEDULE_POLL_SECONDS)
    finally:
        backfill.cancel()
        for task in tasks:
            task.cancel()
        await asyncio.gather(backfill, *tasks, return_exceptions=True)

