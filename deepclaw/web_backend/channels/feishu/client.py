import json
import re
from typing import Any

from deepclaw.web_backend.channels.models import ChannelBinding


class FeishuClientGateway:
    """飞书消息发送网关，优先通过官方 SDK 发送回复消息。"""

    def _import_lark(self):
        import lark_oapi as lark

        return lark

    def _build_client(self, binding: ChannelBinding):
        lark = self._import_lark()
        domain = getattr(lark, "LARK_DOMAIN", None) if binding.config.get("domain") == "lark" else getattr(lark, "FEISHU_DOMAIN", None)
        builder = lark.Client.builder().app_id(binding.credentials["app_id"]).app_secret(binding.credentials["app_secret"])
        if domain is not None:
            builder = builder.domain(domain)
        return builder.build()

    async def reply_text(self, *, binding: ChannelBinding, message_id: str, text: str) -> str:
        from lark_oapi.api.im.v1 import ReplyMessageRequest, ReplyMessageRequestBody

        client = self._build_client(binding)
        request = (
            ReplyMessageRequest.builder()
            .message_id(message_id)
            .request_body(
                ReplyMessageRequestBody.builder()
                .content(json.dumps({"text": text}, ensure_ascii=False))
                .msg_type("text")
                .build()
            )
            .build()
        )
        response = client.im.v1.message.reply(request)
        if not response.success():
            raise RuntimeError(f"Feishu reply failed: code={response.code}, msg={response.msg}")

        data = json.loads(response.raw.content) if getattr(response, "raw", None) is not None else {}
        return str(((data.get("data") or {}).get("message_id")) or message_id)

    async def reply_markdown_card(
        self,
        *,
        binding: ChannelBinding,
        message_id: str,
        text: str,
    ) -> str:
        """回复一张支持 Markdown 渲染的飞书卡片。

        Args:
            binding: 飞书渠道绑定。
            message_id: 要回复的飞书消息 ID。
            text: 卡片中的 Markdown 内容。
        """
        from lark_oapi.api.im.v1 import ReplyMessageRequest, ReplyMessageRequestBody

        client = self._build_client(binding)
        request = (
            ReplyMessageRequest.builder()
            .message_id(message_id)
            .request_body(
                ReplyMessageRequestBody.builder()
                .content(self._markdown_card_content(text))
                .msg_type("interactive")
                .build()
            )
            .build()
        )
        response = client.im.v1.message.reply(request)
        if not response.success():
            raise RuntimeError(f"Feishu card reply failed: code={response.code}, msg={response.msg}")

        data = json.loads(response.raw.content) if getattr(response, "raw", None) is not None else {}
        return str(((data.get("data") or {}).get("message_id")) or message_id)

    async def update_markdown_card(
        self,
        *,
        binding: ChannelBinding,
        message_id: str,
        text: str,
    ) -> None:
        """更新已发送飞书 Markdown 卡片的内容。

        Args:
            binding: 飞书渠道绑定。
            message_id: 要更新的飞书消息 ID。
            text: 卡片中的最新 Markdown 内容。
        """
        from lark_oapi.api.im.v1 import PatchMessageRequest, PatchMessageRequestBody

        client = self._build_client(binding)
        request = (
            PatchMessageRequest.builder()
            .message_id(message_id)
            .request_body(
                PatchMessageRequestBody.builder()
                .content(self._markdown_card_content(text))
                .build()
            )
            .build()
        )
        response = client.im.v1.message.patch(request)
        if not response.success():
            raise RuntimeError(f"Feishu card update failed: code={response.code}, msg={response.msg}")

    @staticmethod
    def _markdown_card_content(text: str) -> str:
        """构造飞书 interactive 卡片的 Markdown 内容。

        Args:
            text: 要渲染的 Markdown 文本。
        """
        return json.dumps(
            {
                "config": {"wide_screen_mode": True},
                "elements": FeishuClientGateway._markdown_card_elements(text),
            },
            ensure_ascii=False,
        )

    @staticmethod
    def _markdown_card_elements(text: str) -> list[dict[str, Any]]:
        """将标准 Markdown 转换为飞书卡片原生元素。

        Args:
            text: 要渲染的标准 Markdown 文本。
        """
        elements: list[dict[str, Any]] = []
        last_end = 0
        table_pattern = re.compile(
            r"((?:^[ \t]*\|.+\|[ \t]*\n)(?:^[ \t]*\|[-:\s|]+\|[ \t]*\n)(?:^[ \t]*\|.+\|[ \t]*\n?)+)",
            re.MULTILINE,
        )
        for match in table_pattern.finditer(text):
            elements.extend(FeishuClientGateway._markdown_text_elements(text[last_end:match.start()]))
            elements.append(FeishuClientGateway._markdown_table_element(match.group(1)))
            last_end = match.end()
        elements.extend(FeishuClientGateway._markdown_text_elements(text[last_end:]))
        return elements or [{"tag": "markdown", "content": text}]

    @staticmethod
    def _markdown_text_elements(text: str) -> list[dict[str, Any]]:
        """将无表格 Markdown 文本转换为飞书标题和正文元素。

        Args:
            text: 不含 Markdown 表格的文本。
        """
        elements: list[dict[str, Any]] = []
        last_end = 0
        for match in re.finditer(r"^#{1,6}\s+(.+)$", text, flags=re.MULTILINE):
            before = text[last_end:match.start()].strip()
            if before:
                elements.append({"tag": "markdown", "content": before})
            elements.append(
                {
                    "tag": "div",
                    "text": {"tag": "lark_md", "content": f"**{match.group(1).strip()}**"},
                }
            )
            last_end = match.end()

        remaining = text[last_end:].strip()
        if remaining:
            elements.append({"tag": "markdown", "content": remaining})
        return elements

    @staticmethod
    def _markdown_table_element(table_text: str) -> dict[str, Any]:
        """将标准 Markdown 表格转换为飞书原生表格元素。

        Args:
            table_text: 包含表头、分隔行和数据行的 Markdown 表格。
        """
        lines = [line.strip() for line in table_text.splitlines() if line.strip()]

        def split_row(line: str) -> list[str]:
            return [cell.strip() for cell in line.strip("|").split("|")]

        def plain_text(value: str) -> str:
            return re.sub(r"(\*\*|__|~~|`)", "", value)

        headers = [plain_text(value) for value in split_row(lines[0])]
        rows = [[plain_text(value) for value in split_row(line)] for line in lines[2:]]
        return {
            "tag": "table",
            "page_size": len(rows) + 1,
            "columns": [
                {"tag": "column", "name": f"c{index}", "display_name": header, "width": "auto"}
                for index, header in enumerate(headers)
            ],
            "rows": [
                {f"c{index}": row[index] if index < len(row) else "" for index in range(len(headers))}
                for row in rows
            ],
        }

    async def create_text(self, *, binding: ChannelBinding, receive_id: str, text: str, receive_id_type: str = "chat_id") -> str:
        from lark_oapi.api.im.v1 import CreateMessageRequest, CreateMessageRequestBody

        client = self._build_client(binding)
        request = (
            CreateMessageRequest.builder()
            .receive_id_type(receive_id_type)
            .request_body(
                CreateMessageRequestBody.builder()
                .receive_id(receive_id)
                .content(json.dumps({"text": text}, ensure_ascii=False))
                .msg_type("text")
                .build()
            )
            .build()
        )
        response = client.im.v1.message.create(request)
        if not response.success():
            raise RuntimeError(f"Feishu send failed: code={response.code}, msg={response.msg}")

        data = json.loads(response.raw.content) if getattr(response, "raw", None) is not None else {}
        return str(((data.get("data") or {}).get("message_id")) or receive_id)

    async def fetch_bot_open_id(self, *, binding: ChannelBinding) -> str | None:
        lark = self._import_lark()
        client = self._build_client(binding)
        request = (
            lark.BaseRequest.builder()
            .http_method(lark.HttpMethod.GET)
            .uri("/open-apis/bot/v3/info")
            .token_types({lark.AccessTokenType.APP})
            .build()
        )
        response = client.request(request)
        if not response.success():
            return None
        data = json.loads(response.raw.content) if getattr(response, "raw", None) is not None else {}
        bot = (data.get("data") or {}).get("bot") or data.get("bot") or {}
        open_id = bot.get("open_id")
        return str(open_id) if open_id else None

    def build_ws_client(self, *, binding: ChannelBinding, event_handler: Any):
        lark = self._import_lark()
        domain = getattr(lark, "LARK_DOMAIN", None) if binding.config.get("domain") == "lark" else getattr(lark, "FEISHU_DOMAIN", None)
        kwargs = {
            "domain": domain,
            "event_handler": event_handler,
            "log_level": getattr(getattr(lark, "LogLevel", object), "INFO", None),
        }
        return lark.ws.Client(
            binding.credentials["app_id"],
            binding.credentials["app_secret"],
            **kwargs,
        )
