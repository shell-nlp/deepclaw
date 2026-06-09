import json
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
