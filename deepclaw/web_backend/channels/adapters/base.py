from typing import Protocol

from deepclaw.web_backend.channels.models import ChannelMessage


class ChannelAdapter(Protocol):
    async def parse_event(self, payload: dict) -> ChannelMessage:
        """Convert a channel webhook payload into a normalized message."""

    async def send_message(self, message: ChannelMessage, text: str) -> str:
        """Send a channel message and return the channel reply message ID."""

    async def edit_message(self, reply_message_id: str, text: str) -> None:
        """Edit a previously sent channel message."""


