"""Agent 层状态基础设施：从 LangGraph checkpoint 历史读取状态信息。"""

from typing import Any


async def collect_message_created_at(
    graph: Any,
    config: dict[str, Any],
) -> dict[str, str]:
    """从 checkpoint 历史推导每条消息第一次出现的创建时间。

    LangGraph 会在每个 super-step 生成一个 checkpoint，并把创建时间写在
    `checkpoint["ts"]` 上（即 `StateSnapshot.created_at`）；消息对象本身没有
    时间字段。这里按时间从新到旧遍历历史，用同一 message_id 覆盖写入，最终
    保留的就是该消息第一次出现的那一步时间。

    Args:
        graph: 已编译且带 checkpointer 的 LangGraph 图。
        config: 指向目标 Thread 的 LangGraph 运行配置。

    Returns:
        message_id 到该消息创建时间（UTC ISO8601 字符串）的映射。
    """
    created_at: dict[str, str] = {}
    async for snapshot in graph.aget_state_history(config):
        snapshot_created_at = snapshot.created_at
        if not snapshot_created_at:
            continue
        values = snapshot.values if isinstance(snapshot.values, dict) else {}
        for message in values.get("messages") or []:
            message_id = getattr(message, "id", None)
            if isinstance(message_id, str):
                created_at[message_id] = snapshot_created_at
    return created_at
