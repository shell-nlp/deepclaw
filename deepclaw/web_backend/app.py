import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from deepclaw.agent_registry import AgentRegistry
from deepclaw.constant import root_dir, workspace_path
from deepclaw.patch.langchain import patch_langchain
from deepclaw.settings import settings
from deepclaw.web_backend.agui.router import router as agui_router
from deepclaw.web_backend.agent.run_store import get_run_store
from deepclaw.web_backend.auth.router import router as auth_router
from deepclaw.web_backend.auth.service import get_auth_service
from deepclaw.web_backend.channels.router import router as channels_router
from deepclaw.web_backend.channels.weixin_clawbot.lifespan import channel_lifespan
from deepclaw.web_backend.common.errors import BusinessRuleError
from deepclaw.web_backend.common.agui_runs import (
    get_agui_agents_path,
    get_agui_runs_path,
    runtime_router,
)
from deepclaw.web_backend.knowledge_bases.router import (
    router as knowledge_bases_router,
)
from deepclaw.web_backend.skills.router import router as skills_router


def setup_observability() -> None:
    try:
        if os.getenv("PHOENIX_COLLECTOR_ENDPOINT"):
            from phoenix.otel import register  # pyright: ignore[reportMissingImports]

            register(
                project_name="default",
                auto_instrument=True,
            )
    except ImportError:
        logger.warning("Phoenix 未安装，跳过可观测性初始化。")



async def handle_business_rule_error(
    request: Request,
    exc: BusinessRuleError,
) -> JSONResponse:
    """把业务规则异常转换为统一 HTTP 错误响应。

    Args:
        request: 当前 FastAPI 请求。
        exc: 业务规则异常。

    Returns:
        包含 detail 字段的 JSON 响应。
    """
    return JSONResponse(status_code=exc.status_code, content={"detail": str(exc)})


async def init_agent_env(app: FastAPI) -> None:
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
        app.state.agent_store_ctx = store_ctx
        app.state.store = store
        logger.info("使用 AsyncPostgresStore 作为长期记忆")
    else:
        from langgraph.checkpoint.memory import InMemorySaver
        from langgraph.store.memory import InMemoryStore

        checkpointer = InMemorySaver()
        app.state.agent_checkpointer_pool = None
        logger.info("使用 InMemorySaver 作为检查点")

        store = InMemoryStore()
        app.state.agent_store_ctx = None
        logger.info("使用 InMemoryStore 作为长期记忆")

    app.state.checkpointer = checkpointer
    app.state.store = store


def register_frontend_routes(app: FastAPI) -> None:
    """在 API 路由之后再挂载前端静态资源，避免吞掉 POST API 请求。"""

    if getattr(app.state, "frontend_routes_registered", False):
        return

    next_frontend_path = root_dir / "frontend" / "out"
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


@asynccontextmanager
async def app_lifespan(app: FastAPI):
    setup_observability()
    patch_langchain()
    await init_agent_env(app)
    app.state.agent_registry = AgentRegistry.discover()
    await get_run_store().initialize()
    register_frontend_routes(app)
    logger.info(
        "AG-UI runs={} | agents={}",
        get_agui_runs_path(),
        get_agui_agents_path(),
    )
    await get_auth_service().bootstrap_admin_if_needed()
    try:
        async with channel_lifespan():
            yield
    finally:
        checkpointer_pool = getattr(app.state, "agent_checkpointer_pool", None)
        if checkpointer_pool is not None:
            await checkpointer_pool.close()
        store_ctx = getattr(app.state, "agent_store_ctx", None)
        if store_ctx is not None:
            await store_ctx.__aexit__(None, None, None)


def register_charts_static(app: FastAPI) -> None:
    """挂载 /charts 目录，使图表图片可通过 URL 访问。"""
    charts_dir = workspace_path / "charts"
    charts_dir.mkdir(parents=True, exist_ok=True)
    for route in app.routes:
        if hasattr(route, "path") and route.path == "/charts":
            return
    app.mount(
        "/charts",
        StaticFiles(directory=str(charts_dir)),
        name="charts",
    )


def _register_exported_html_routes(app: FastAPI, frontend_dir: Path) -> None:
    for html_file in frontend_dir.glob("*.html"):
        if html_file.name in {"index.html", "404.html"}:
            continue

        route_path = f"/{html_file.stem}"

        async def serve_exported_page(file_path=html_file):
            return FileResponse(file_path)

        app.get(route_path, include_in_schema=False)(serve_exported_page)


def create_app() -> FastAPI:
    app = FastAPI(lifespan=app_lifespan)
    app.add_exception_handler(BusinessRuleError, handle_business_rule_error)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(auth_router)
    app.include_router(agui_router)
    app.include_router(channels_router)
    app.include_router(skills_router)
    app.include_router(knowledge_bases_router)
    app.include_router(runtime_router)

    register_charts_static(app)
    return app
