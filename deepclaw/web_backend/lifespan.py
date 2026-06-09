import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from loguru import logger

from deepclaw.patch.langchain import patch_langchain
from deepclaw.web_backend.auth.service import get_auth_service
from deepclaw.web_backend.channels.weixin_clawbot.lifespan import channel_lifespan


def setup_observability() -> None:
    try:
        if os.getenv("PHOENIX_COLLECTOR_ENDPOINT"):
            from phoenix.otel import register

            register(
                project_name="default",
                auto_instrument=True,
            )
    except ImportError:
        logger.warning("Phoenix 未安装，跳过可观测性初始化。")


@asynccontextmanager
async def app_lifespan(app: FastAPI):
    setup_observability()
    patch_langchain()
    get_auth_service().bootstrap_admin_if_needed()
    async with channel_lifespan():
        yield

