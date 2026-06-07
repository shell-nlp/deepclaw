import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from deepclaw.web_backend.agent.router import create_agent_router
from deepclaw.web_backend.auth.router import create_auth_router
from deepclaw.web_backend.channels.router import create_channels_router
from deepclaw.web_backend.rag.router import create_rag_router
from deepclaw.web_backend.auth.service import get_auth_service
from deepclaw.web_backend.channels.lifespan import channel_lifespan
from deepclaw.constant import root_dir
from deepclaw.patch.langchain import patch_langchain
from deepclaw.settings import settings
from deepclaw.web_backend.knowledge_bases.router import (
    create_knowledge_bases_router,
)
from deepclaw.web_backend.skills.router import create_skills_router
from loguru import logger


def setup_observability() -> None:
    try:
        if os.getenv("PHOENIX_COLLECTOR_ENDPOINT"):
            from phoenix.otel import register

            register(
                project_name="default",
                auto_instrument=True,
            )
    except ImportError:
        pass


def init_agent_env():
    from langgraph.checkpoint.memory import InMemorySaver

    checkpointer = InMemorySaver()
    if settings.PG_DATABASE_URL:
        from langgraph.store.postgres import PostgresStore

        store_ctx = PostgresStore.from_conn_string(settings.PG_DATABASE_URL)
        store = store_ctx.__enter__()
        store.setup()
        logger.info("使用PostgresStore作为长期记忆")
    else:
        from langgraph.store.memory import InMemoryStore

        store = InMemoryStore()
        logger.info("使用InMemoryStore作为长期记忆")
    return checkpointer, store


def _register_exported_html_routes(app: FastAPI, frontend_dir: Path) -> None:
    for html_file in frontend_dir.glob("*.html"):
        if html_file.name in {"index.html", "404.html"}:
            continue

        route_path = f"/{html_file.stem}"

        async def serve_exported_page(file_path=html_file):
            return FileResponse(file_path)

        app.get(route_path, include_in_schema=False)(serve_exported_page)


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_observability()
    patch_langchain()
    get_auth_service().bootstrap_admin_if_needed()
    async with channel_lifespan():
        yield


def create_app() -> FastAPI:
    app = FastAPI(lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    # Register API routes before mounting the frontend; otherwise StaticFiles
    # would catch /api/* requests and return 405 for POST.
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


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=7869)

