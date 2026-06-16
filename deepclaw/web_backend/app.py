from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger

from deepclaw.constant import root_dir
from deepclaw.settings import settings
from deepclaw.web_backend.agent.router import create_agent_router
from deepclaw.web_backend.auth.router import create_auth_router
from deepclaw.web_backend.channels.router import create_channels_router
from deepclaw.web_backend.knowledge_bases.router import (
    create_knowledge_bases_router,
)
from deepclaw.web_backend.lifespan import app_lifespan
from deepclaw.web_backend.rag.router import create_rag_router
from deepclaw.web_backend.skills.router import create_skills_router


def init_agent_env():
    from langgraph.checkpoint.memory import InMemorySaver

    checkpointer = InMemorySaver()
    if settings.PG_DATABASE_URL:
        from langgraph.store.postgres import PostgresStore

        # 使用连接池而不是单连接：
        # 池子默认按 max_lifetime=3600s / max_idle=600s 自动回收连接，
        # 避免 server 端因空闲超时或重启杀掉长连接后所有请求都失败
        store_ctx = PostgresStore.from_conn_string(
            settings.PG_DATABASE_URL,
            pool_config={"min_size": 1, "max_size": 10},
        )
        store = store_ctx.__enter__()
        store.setup()
        # 关键：from_conn_string 是 @contextmanager，连接 / 连接池资源都握在
        # generator frame 里。如果不把 store_ctx 挂在 store 上，
        # init_agent_env() 返回后 store_ctx 会被立即 GC，触发 __exit__ 把连接关掉，
        # 后续 store.put / store.batch 会报 "the connection is closed"。
        store._store_cm = store_ctx
        logger.info("使用 PostgresStore 作为长期记忆")
    else:
        from langgraph.store.memory import InMemoryStore

        store = InMemoryStore()
        logger.info("使用 InMemoryStore 作为长期记忆")
    return checkpointer, store


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
    checkpointer, store = init_agent_env()
    app.include_router(create_auth_router())
    app.include_router(create_agent_router(checkpointer, store))
    app.include_router(create_rag_router(checkpointer, store))
    app.include_router(create_channels_router())
    app.include_router(create_skills_router())
    app.include_router(create_knowledge_bases_router())
    next_frontend_path = root_dir / "frontend" / "out"
    if next_frontend_path.exists():
        _register_exported_html_routes(app, next_frontend_path)
        app.mount(
            "/",
            StaticFiles(
                directory=next_frontend_path,
                html=True,
            ),
            name="next_frontend",
        )
    return app
