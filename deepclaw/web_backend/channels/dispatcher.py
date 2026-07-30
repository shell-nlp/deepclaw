import time
from collections.abc import AsyncIterator

from deepclaw.web_backend.channels.adapters.base import ChannelAdapter
from deepclaw.web_backend.channels.models import (
    AgentEvent,
    ChannelMessage,
    ReplyMode,
)


INTERRUPT_FALLBACK = "该操作需要人工确认，当前渠道暂不支持处理。"
STREAMING_PLACEHOLDER = "正在处理..."
EMPTY_REPLY = "没有可发送的回复。"
TOOL_OUTPUT_STATUS = "工具已完成，正在整理结果..."


class ResponseDispatcher:
    def __init__(self, min_interval_seconds: float = 0.8, min_chars: int = 20):
        self.min_interval_seconds = min_interval_seconds
        self.min_chars = min_chars

    async def dispatch(
        self,
        *,
        adapter: ChannelAdapter,
        message: ChannelMessage,
        reply_mode: ReplyMode,
        events: AsyncIterator[AgentEvent],
    ) -> None:
        if reply_mode == "streaming":
            await self._dispatch_streaming(adapter, message, events)
            return
        await self._dispatch_final(adapter, message, events)

    async def _dispatch_final(
        self,
        adapter: ChannelAdapter,
        message: ChannelMessage,
        events: AsyncIterator[AgentEvent],
    ) -> None:
        parts: list[str] = []
        async for event in events:
            if event.event == "__interrupt__":
                await adapter.send_message(message, INTERRUPT_FALLBACK)
                return
            if event.event != "token" or not event.data:
                continue
            token = event.data.get("token")
            if token:
                parts.append(str(token))

        await adapter.send_message(message, "".join(parts) or EMPTY_REPLY)

    async def _dispatch_streaming(
        self,
        adapter: ChannelAdapter,
        message: ChannelMessage,
        events: AsyncIterator[AgentEvent],
    ) -> None:
        if getattr(adapter, "supports_message_stream", True) is False:
            await self._dispatch_streaming_with_typing(adapter, message, events)
            return

        start_message = getattr(adapter, "start_message", None)
        if start_message is not None:
            reply_message_id = await start_message(message, STREAMING_PLACEHOLDER)
        else:
            reply_message_id = await adapter.send_message(message, STREAMING_PLACEHOLDER)
        parts: list[str] = []
        last_text = ""
        last_edit_at = time.monotonic()

        async for event in events:
            if event.event == "__interrupt__":
                await adapter.edit_message(reply_message_id, INTERRUPT_FALLBACK)
                return
            process_status = self._process_status(event)
            if process_status is not None:
                status_text = "".join(parts) + ("\n\n" if parts else "") + process_status
                await adapter.edit_message(reply_message_id, status_text)
                last_text = ""
                last_edit_at = time.monotonic()
                continue
            if event.event != "token" or not event.data:
                continue
            token = event.data.get("token")
            if not token:
                continue

            parts.append(str(token))
            text = "".join(parts)
            if self._should_edit(text, last_text, last_edit_at):
                await adapter.edit_message(reply_message_id, text)
                last_text = text
                last_edit_at = time.monotonic()

        final_text = "".join(parts) or EMPTY_REPLY
        if final_text != last_text:
            await adapter.edit_message(reply_message_id, final_text)
        finish_message = getattr(adapter, "finish_message", None)
        if finish_message is not None:
            await finish_message(reply_message_id, final_text)

    async def _dispatch_streaming_with_typing(
        self,
        adapter: ChannelAdapter,
        message: ChannelMessage,
        events: AsyncIterator[AgentEvent],
    ) -> None:
        start_typing = getattr(adapter, "start_typing", None)
        stop_typing = getattr(adapter, "stop_typing", None)
        if start_typing is not None:
            await start_typing(message)

        parts: list[str] = []
        try:
            async for event in events:
                if event.event == "__interrupt__":
                    await adapter.send_message(message, INTERRUPT_FALLBACK)
                    return
                if event.event != "token" or not event.data:
                    continue
                token = event.data.get("token")
                if token:
                    parts.append(str(token))

            await adapter.send_message(message, "".join(parts) or EMPTY_REPLY)
        finally:
            if stop_typing is not None:
                await stop_typing(message)

    def _should_edit(self, text: str, last_text: str, last_edit_at: float) -> bool:
        new_chars = len(text) - len(last_text)
        interval_elapsed = time.monotonic() - last_edit_at >= self.min_interval_seconds
        boundary = text.endswith(("\n", "。", "！", "？", ".", "!", "?"))
        return new_chars >= self.min_chars or interval_elapsed or boundary

    def _process_status(self, event: AgentEvent) -> str | None:
        """将工具调用和工具输出事件转换为用户可见的过程提示。

        Args:
            event: Agent SSE 输出的渠道事件。
        """
        if event.event == "tool_output":
            return TOOL_OUTPUT_STATUS
        if event.event != "tool_calls" or not isinstance(event.data, dict):
            return None

        tool_calls = event.data.get("tool_calls")
        if not isinstance(tool_calls, list):
            return "正在调用工具..."
        names = [self._tool_name(tool_call) for tool_call in tool_calls]
        visible_names = [name for name in names if name]
        return f"正在调用工具：{'、'.join(visible_names)}" if visible_names else "正在调用工具..."

    @staticmethod
    def _tool_name(tool_call: object) -> str | None:
        """从 SSE 工具调用载荷中提取可展示的工具名称。

        Args:
            tool_call: 单个工具调用对象。
        """
        if not isinstance(tool_call, dict):
            return None
        name = tool_call.get("name")
        if isinstance(name, str) and name:
            return name
        function = tool_call.get("function")
        if isinstance(function, dict):
            function_name = function.get("name")
            if isinstance(function_name, str) and function_name:
                return function_name
        return None

