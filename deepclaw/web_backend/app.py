from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response

from deepclaw.middleware.chart import storage as chart_storage
from deepclaw.settings import settings
from deepclaw.web_backend.agui.runtime import AgentRuntimeCache
from deepclaw.web_backend.agui.router import router as agui_router
from deepclaw.web_backend.auth.router import router as auth_router
from deepclaw.web_backend.channels.router import router as channels_router
from deepclaw.web_backend.common.agui_runs import runtime_router
from deepclaw.web_backend.common.errors import BusinessRuleError
from deepclaw.web_backend.knowledge_bases.router import (
    router as knowledge_bases_router,
)
from deepclaw.web_backend.lifespan import app_lifespan
from deepclaw.web_backend.skills.router import router as skills_router


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


def register_charts_static(app: FastAPI) -> None:
    """挂载图表对象读取路由，使默认路径和自定义前缀都可访问图片。

    Args:
        app: 待挂载图表静态路由的 FastAPI 应用。
    """
    chart_routes = [("/charts", "charts")]
    configured_url = settings.CHART_PUBLIC_URL.strip()
    configured_path = (
        urlsplit(configured_url).path
        if configured_url.startswith(("http://", "https://"))
        else configured_url
    ).rstrip("/")
    if configured_path and configured_path not in {"", "/", "/charts"}:
        chart_routes.append((f"{configured_path}/charts", "public_charts"))

    existing_paths = {getattr(route, "path", None) for route in app.routes}

    def serve_configured_chart(file_name: str) -> Response:
        """从对象存储返回图表 PNG。

        Args:
            file_name: 图表文件名。

        Returns:
            Response: PNG 图片响应。

        Raises:
            HTTPException: 文件名非法或对象不存在时返回 404。
        """
        try:
            chart_data = chart_storage.read_chart_png(file_name)
        except (FileNotFoundError, ValueError) as exc:
            raise HTTPException(status_code=404, detail="图表不存在") from exc
        return Response(
            content=chart_data,
            media_type="image/png",
            headers={"Cache-Control": "public, max-age=31536000, immutable"},
        )

    for route_path, route_name in chart_routes:
        endpoint_path = f"{route_path}/{{file_name}}"
        if endpoint_path in existing_paths:
            continue
        app.add_api_route(
            endpoint_path,
            serve_configured_chart,
            methods=["GET"],
            include_in_schema=False,
            name=route_name,
        )


def create_app() -> FastAPI:
    """创建 FastAPI 应用并完成路由装配。

    Returns:
        已完成路由与生命周期装配的应用实例。
    """
    app = FastAPI(lifespan=app_lifespan)
    app.state.agent_runtime_cache = AgentRuntimeCache()
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
