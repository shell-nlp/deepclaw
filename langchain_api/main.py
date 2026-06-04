import asyncio
import os
import sys
from contextlib import asynccontextmanager, suppress
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from langchain_api.api.routers import (
    create_agent_router,
    create_channels_router,
    create_rag_router,
)
from langchain_api.channels.weixin_startup import (
    WeixinClawBotRuntime,
    fetch_startup_qrcode,
)
from langchain_api.channels.config import weixin_clawbot_settings
from langchain_api.constant import root_dir
from langchain_api.patch.langchain import patch_langchain
from langchain_api.settings import settings
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 设置可观测性
    setup_observability()
    patch_langchain()
    weixin_task = None
    if weixin_clawbot_settings.WEIXIN_CLAWBOT_PRINT_QRCODE_ON_STARTUP:
        try:
            qrcode = await fetch_startup_qrcode()
            if qrcode.get("qrcode_url"):
                logger.info("微信 ClawBot 登录二维码链接：\n{}", qrcode["qrcode_url"])
            else:
                logger.warning("微信 ClawBot 未返回可展示的二维码链接")
            if (
                weixin_clawbot_settings.WEIXIN_CLAWBOT_AUTO_POLL_ON_STARTUP
                and qrcode.get("qrcode")
            ):
                runtime = WeixinClawBotRuntime(
                    qrcode=str(qrcode["qrcode"]),
                    login_poll_interval_seconds=weixin_clawbot_settings.WEIXIN_CLAWBOT_LOGIN_POLL_INTERVAL_SECONDS,
                    message_poll_interval_seconds=weixin_clawbot_settings.WEIXIN_CLAWBOT_MESSAGE_POLL_INTERVAL_SECONDS,
                )
                weixin_task = asyncio.create_task(runtime.run_forever())
        except Exception as exc:
            logger.warning("获取微信 ClawBot 登录二维码失败：{}", exc)
    try:
        yield
    finally:
        if weixin_task is not None:
            weixin_task.cancel()
            with suppress(asyncio.CancelledError):
                await weixin_task


def create_app() -> FastAPI:
    app = FastAPI(lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    # 先注册 API 路由，再挂载前端静态站点；否则 "/" 的 StaticFiles
    # 会抢先匹配 /api/*，把 POST 请求错误地返回成 405。
    checkpointer, store = init_agent_env()
    app.include_router(create_agent_router(checkpointer, store))
    app.include_router(create_rag_router(checkpointer, store))
    app.include_router(create_channels_router())
    next_frontend_path = root_dir / "frontend" / "out"
    if next_frontend_path.exists():
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
