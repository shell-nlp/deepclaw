import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from deepclaw.agent_registry import AgentRegistry
from deepclaw.constant import ROOT_DIR
from deepclaw.settings import settings
from deepclaw.web_backend.agui.runtime import AgentRuntimeCache
from deepclaw.web_backend.agent.run_store import (
    get_run_store,
    restore_threads_from_checkpoints,
)
from deepclaw.web_backend.auth.service import get_auth_service
from deepclaw.web_backend.channels.weixin_clawbot.lifespan import channel_lifespan
from deepclaw.web_backend.common.agui_runs import (
    get_agui_agents_path,
    get_agui_runs_path,
)
from deepclaw.web_backend.knowledge_bases.service import get_knowledge_base_manager


def validate_runtime_settings() -> None:
    """在启动阶段校验关键配置组合，缺依赖时快速失败。

    Raises:
        RuntimeError: 配置组合缺少必需依赖时抛出。
    """
    problems: list[str] = []

    if settings.VECTOR_STORE_BACKEND == "pgsql" and not settings.PG_DATABASE_URL:
        problems.append("VECTOR_STORE_BACKEND=pgsql 时必须配置 PG_DATABASE_URL。")
    if settings.VECTOR_STORE_BACKEND == "elasticsearch" and not settings.ES_URL:
        problems.append("VECTOR_STORE_BACKEND=elasticsearch 时必须配置 ES_URL。")
    if settings.OBJECT_STORAGE_PROVIDER == "minio":
        missing_minio = [
            name
            for name, value in (
                ("MINIO_ENDPOINT_URL", settings.MINIO_ENDPOINT_URL),
                ("MINIO_ACCESS_KEY", settings.MINIO_ACCESS_KEY),
                ("MINIO_SECRET_KEY", settings.MINIO_SECRET_KEY),
            )
            if not value
        ]
        if missing_minio:
            problems.append(
                "OBJECT_STORAGE_PROVIDER=minio 时必须配置 "
                + "、".join(missing_minio)
                + "。"
            )

    if problems:
        raise RuntimeError("运行时配置校验失败：\n- " + "\n- ".join(problems))


def setup_observability() -> None:
    """按环境变量初始化 Phoenix 可观测性。"""
    try:
        if os.getenv("PHOENIX_COLLECTOR_ENDPOINT"):
            from phoenix.otel import register  # pyright: ignore[reportMissingImports]

            register(
                project_name="default",
                auto_instrument=True,
            )
    except ImportError:
        logger.warning("Phoenix 未安装，跳过可观测性初始化。")


async def init_agent_env(app: FastAPI) -> None:
    """初始化 LangGraph 检查点与长期记忆存储。

    Args:
        app: 当前 FastAPI 应用。
    """
    checkpointer = None
    store = None
    if settings.PG_DATABASE_URL:
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

        checkpointer_pool = AsyncConnectionPool(
            settings.PG_DATABASE_URL,
            min_size=1,
            max_size=10,
            kwargs={
                "autocommit": True,
                "prepare_threshold": 0,
                "row_factory": dict_row,
            },
            check=AsyncConnectionPool.check_connection,
            open=False,
        )
        await checkpointer_pool.open(wait=True)
        checkpointer = AsyncPostgresSaver(checkpointer_pool)
        await checkpointer.setup()

        app.state.agent_checkpointer_pool = checkpointer_pool
        app.state.checkpointer = checkpointer
        logger.info("使用带连接池的 AsyncPostgresSaver 作为检查点")
        # ------------------------------------------------------
        from langgraph.store.postgres.aio import AsyncPostgresStore

        store_ctx = AsyncPostgresStore.from_conn_string(
            settings.PG_DATABASE_URL,
            pool_config={
                "min_size": 1,
                "max_size": 10,
                "check": AsyncConnectionPool.check_connection,
            },
        )
        store = await store_ctx.__aenter__()
        await store.setup()
        app.state.langgraph_store_ctx = store_ctx
        app.state.store = store
        logger.info("使用 AsyncPostgresStore 作为长期记忆")
    else:
        from langgraph.checkpoint.memory import InMemorySaver
        from langgraph.store.memory import InMemoryStore

        checkpointer = InMemorySaver()
        app.state.agent_checkpointer_pool = None
        logger.info("使用 InMemorySaver 作为检查点")

        store = InMemoryStore()
        app.state.langgraph_store_ctx = None
        logger.info("使用 InMemoryStore 作为长期记忆")

    app.state.checkpointer = checkpointer
    app.state.store = store


def register_frontend_routes(app: FastAPI) -> None:
    """在 API 路由之后再挂载前端静态资源，避免吞掉 POST API 请求。

    Args:
        app: 当前 FastAPI 应用。
    """
    if getattr(app.state, "frontend_routes_registered", False):
        return

    next_frontend_path = ROOT_DIR / "frontend" / "out"
    if not next_frontend_path.exists():
        return

    _register_exported_html_routes(app, next_frontend_path)
    app.mount(
        "/",
        StaticFiles(
            directory=next_frontend_path,
            html=True,
        ),
        name="next_frontend",
    )
    app.state.frontend_routes_registered = True


def _register_exported_html_routes(app: FastAPI, frontend_dir: Path) -> None:
    """为导出的非首页 HTML 注册独立路由。

    Args:
        app: 当前 FastAPI 应用。
        frontend_dir: Next.js 静态导出目录。
    """
    for html_file in frontend_dir.glob("*.html"):
        if html_file.name in {"index.html", "404.html"}:
            continue

        route_path = f"/{html_file.stem}"

        async def serve_exported_page(file_path=html_file):
            return FileResponse(file_path)

        app.get(route_path, include_in_schema=False)(serve_exported_page)


@asynccontextmanager
async def app_lifespan(app: FastAPI):
    """管理应用启动初始化与关闭清理。

    Args:
        app: 当前 FastAPI 应用。
    """
    validate_runtime_settings()
    setup_observability()
    await init_agent_env(app)
    app.state.agent_registry = AgentRegistry.discover()
    run_store = get_run_store()
    await run_store.initialize()
    default_agent = app.state.agent_registry.resolve(None)
    await restore_threads_from_checkpoints(
        run_store,
        app.state.checkpointer,
        default_agent_id=default_agent.agent_id,
    )
    runtime_cache = getattr(app.state, "agent_runtime_cache", None)
    if runtime_cache is None:
        runtime_cache = AgentRuntimeCache()
        app.state.agent_runtime_cache = runtime_cache
    await runtime_cache.preload(
        app=app,
        agents=app.state.agent_registry.list_agents(),
        checkpointer=app.state.checkpointer,
        store=app.state.store,
        run_store=run_store,
    )
    register_frontend_routes(app)
    logger.info(
        "AG-UI runs={} | agents={}",
        get_agui_runs_path(),
        get_agui_agents_path(),
    )
    await get_auth_service().bootstrap_admin_if_needed()
    upload_manager = get_knowledge_base_manager()
    await upload_manager.start_upload_workers()
    try:
        async with channel_lifespan():
            yield
    finally:
        await upload_manager.stop_upload_workers()
        runtime_cache = getattr(app.state, "agent_runtime_cache", None)
        if runtime_cache is not None:
            await runtime_cache.close()
        await get_run_store().close()
        checkpointer_pool = getattr(app.state, "agent_checkpointer_pool", None)
        if checkpointer_pool is not None:
            await checkpointer_pool.close()
        store_ctx = getattr(app.state, "langgraph_store_ctx", None)
        if store_ctx is not None:
            await store_ctx.__aexit__(None, None, None)
