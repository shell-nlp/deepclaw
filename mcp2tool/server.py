from mcp.server.fastmcp import FastMCP, Context
from loguru import logger


mcp = FastMCP("Math", host="0.0.0.0", port=48000)


@mcp.tool()
def add(a: int, b: int, ctx: Context) -> int:
    """Add two numbers"""
    meta = ctx.request_context.meta
    extra_meta: dict[str, object] = {}
    if meta is not None:
        extra_meta = meta.model_extra or {}
    user_id = extra_meta.get("userId") or "unknown"
    logger.info(f"User ID: {user_id}")
    return a + b


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
