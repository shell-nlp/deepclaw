import asyncio

from loguru import logger
from mcp.server.fastmcp import Context, FastMCP


mcp = FastMCP("Math", host="0.0.0.0", port=48000)


@mcp.tool()
async def add(a: int, b: int, ctx: Context) -> int:
    """Add two numbers with streamed progress over SSE."""
    meta = ctx.request_context.meta
    extra_meta: dict[str, object] = {}
    if meta is not None:
        extra_meta = meta.model_extra or {}
    user_id = extra_meta.get("userId") or "unknown"
    logger.warning(f"User ID: {user_id}")

    steps = 5
    for i in range(1, steps + 1):
        await ctx.info(f"正在计算 step {i}/{steps}, user={user_id}")
        # 客户端 call_tool 传入 progress_callback 时才会真正发出
        await ctx.report_progress(
            progress=i,
            total=steps,
            message=f"计算中 {i}/{steps}",
        )
        await asyncio.sleep(0.5)

    await ctx.info("计算完成")
    return a + b


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
