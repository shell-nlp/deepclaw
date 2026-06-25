import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger

from deepclaw.constant import root_dir
from deepclaw.patch.langchain import patch_langchain
from deepclaw.settings import settings
from deepclaw.web_backend.agent.router import create_agent_router
from deepclaw.web_backend.auth.router import create_auth_router
from deepclaw.web_backend.auth.service import get_auth_service
from deepclaw.web_backend.channels.router import create_channels_router
from deepclaw.web_backend.channels.weixin_clawbot.lifespan import channel_lifespan
from deepclaw.web_backend.knowledge_bases.router import (
    create_knowledge_bases_router,
)
from deepclaw.web_backend.rag.router import create_rag_router
from deepclaw.web_backend.skills.router import create_skills_router


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


async def init_agent_env(app: FastAPI) -> None:
    checkpointer = None
    store = None
    if settings.PG_DATABASE_URL:
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

        _ctx = AsyncPostgresSaver.from_conn_string(
            settings.PG_DATABASE_URL,
        )
        checkpointer = await _ctx.__aenter__()
        await checkpointer.setup()
        # 关键：AsyncPostgresSaver.from_conn_string() 返回的是异步上下文管理器。
        # 如果不把 _ctx 挂到 app.state 上保活，函数返回后它可能被回收并触发 __aexit__，
        # 后续请求读 checkpoint 时就会报 "the connection is closed"。
        app.state.agent_checkpointer_ctx = _ctx
        logger.info("使用 AsyncPostgresSaver 作为检查点")
        # ------------------------------------------------------
        from langgraph.store.postgres.aio import AsyncPostgresStore

        # 使用连接池而不是单连接：
        # 池子默认按 max_lifetime=3600s / max_idle=600s 自动回收连接，
        # 避免 server 端因空闲超时或重启杀掉长连接后所有请求都失败
        store_ctx = AsyncPostgresStore.from_conn_string(
            settings.PG_DATABASE_URL,
            pool_config={"min_size": 1, "max_size": 10},
        )
        store = await store_ctx.__aenter__()
        await store.setup()
        # 关键：from_conn_string 是 @contextmanager，连接 / 连接池资源都握在
        # generator frame 里。如果不把 store_ctx 挂在 store 上，
        # init_agent_env() 返回后 store_ctx 会被立即 GC，触发 __exit__ 把连接关掉，
        # 后续 store.put / store.batch 会报 "the connection is closed"。
        store._store_cm = store_ctx
        app.state.agent_store_ctx = store_ctx
        logger.info("使用 AsyncPostgresStore 作为长期记忆")
    else:
        from langgraph.checkpoint.memory import InMemorySaver
        from langgraph.store.memory import InMemoryStore

        checkpointer = InMemorySaver()
        app.state.agent_checkpointer_ctx = None
        logger.info("使用 InMemorySaver 作为检查点")

        store = InMemoryStore()
        app.state.agent_store_ctx = None
        logger.info("使用 InMemoryStore 作为长期记忆")

    app.state.checkpointer = checkpointer
    app.state.store = store


def register_agent_routes(app: FastAPI) -> None:
    """在生命周期启动阶段注册依赖 agent 运行时的路由。"""

    if getattr(app.state, "agent_routes_registered", False):
        return

    app.include_router(create_agent_router(app.state.checkpointer, app.state.store))
    app.include_router(create_rag_router(app.state.checkpointer, app.state.store))
    app.state.agent_routes_registered = True


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
    register_agent_routes(app)
    register_frontend_routes(app)
    await get_auth_service().bootstrap_admin_if_needed()
    try:
        async with channel_lifespan():
            yield
    finally:
        checkpointer_ctx = getattr(app.state, "agent_checkpointer_ctx", None)
        if checkpointer_ctx is not None:
            await checkpointer_ctx.__aexit__(None, None, None)
        store_ctx = getattr(app.state, "agent_store_ctx", None)
        if store_ctx is not None:
            store_ctx.__exit__(None, None, None)


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
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(create_auth_router())
    app.include_router(create_channels_router())
    app.include_router(create_skills_router())
    app.include_router(create_knowledge_bases_router())
    return app
