from collections.abc import Awaitable
from typing import Any

import httpx
from fastapi import HTTPException

from deepclaw.web_backend.auth.dependencies import CurrentActor
from deepclaw.web_backend.channels.common import (
    accessible_binding_user_id,
    ensure_binding_access,
    ensure_binding_owner_or_manager_match,
    ensure_runtime_state_access,
    manager_user_id_from_actor,
)
from deepclaw.web_backend.channels.models import ChannelBinding, ChannelMessage
from deepclaw.web_backend.channels.service import ChannelService
from deepclaw.web_backend.channels.store import ChannelStore, get_channel_store
from deepclaw.web_backend.channels.weixin_clawbot.adapter import (
    CHANNEL as WEIXIN_CLAWBOT_CHANNEL,
    WeixinClawBotAdapter,
)
from deepclaw.web_backend.channels.weixin_clawbot.client import (
    WeixinClawBotClient,
    WeixinClawBotRequestError,
    WeixinClawBotRequestTimeoutError,
)
from deepclaw.web_backend.channels.weixin_clawbot.lifespan import (
    start_weixin_binding_runtime,
    start_weixin_clawbot_runtime,
    stop_weixin_binding_runtime,
    stop_weixin_clawbot_runtime,
)
from deepclaw.web_backend.channels.weixin_clawbot.runtime import (
    weixin_binding_state_key,
)
from deepclaw.web_backend.channels.weixin_clawbot.schemas import (
    WeixinClawBotBoundUserList,
    WeixinClawBotBoundUserRead,
)
from deepclaw.web_backend.channels.weixin_clawbot.state import (
    mask_token,
    runtime_state_manager_user_id,
    weixin_clawbot_user_id_from_state_key,
    weixin_clawbot_user_state_key,
)


async def call_weixin_clawbot_api(
    awaitable: Awaitable[dict[str, Any]],
) -> dict[str, Any]:
    """执行微信 ClawBot 上游请求并把网络异常转换为 HTTP 异常。

    Args:
        awaitable: 待执行的上游请求协程。

    Returns:
        上游返回的数据字典。

    Raises:
        HTTPException: 上游超时返回 504，其余请求失败返回 502。
    """
    try:
        return await awaitable
    except WeixinClawBotRequestTimeoutError as exc:
        raise HTTPException(
            status_code=504,
            detail="Weixin ClawBot request timed out. Please try again.",
        ) from exc
    except WeixinClawBotRequestError as exc:
        raise HTTPException(
            status_code=502,
            detail="Weixin ClawBot request failed. Please check the upstream service.",
        ) from exc
    except httpx.TimeoutException as exc:
        raise HTTPException(
            status_code=504,
            detail="Weixin ClawBot request timed out. Please try again.",
        ) from exc
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=502,
            detail="Weixin ClawBot request failed. Please check the upstream service.",
        ) from exc


class WeixinClawBotService:
    """微信 ClawBot 绑定、二维码登录与运行态编排服务。"""

    def __init__(
        self,
        *,
        store: ChannelStore | None = None,
        service: ChannelService | None = None,
        client: WeixinClawBotClient | None = None,
    ) -> None:
        self.store = store or get_channel_store()
        self.channel_service = service or ChannelService(store=self.store)
        self._weixin_client = client

    def _client(self) -> WeixinClawBotClient:
        """返回当前请求使用的微信 ClawBot 客户端。

        Args:
            无。

        Returns:
            注入的客户端实例，未注入时新建一个。
        """
        return self._weixin_client or WeixinClawBotClient()

    async def _require_binding(
        self,
        *,
        actor: CurrentActor,
        binding_id: int,
    ) -> ChannelBinding:
        """读取绑定并校验当前用户访问权限。

        Args:
            actor: 当前鉴权主体。
            binding_id: 渠道绑定 ID。

        Returns:
            校验通过的渠道绑定。

        Raises:
            HTTPException: 绑定不存在或无权访问时抛出 404。
        """
        binding = await self.store.get_binding(binding_id)
        ensure_binding_access(
            actor=actor,
            binding=binding,
            not_found_detail="Weixin ClawBot binding not found",
        )
        return binding

    async def _binding_qrcode_response(
        self,
        *,
        binding: ChannelBinding,
        actor: CurrentActor,
        raw: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """刷新绑定二维码并返回可直接响应给前端的载荷。

        Args:
            binding: 待刷新二维码的渠道绑定。
            actor: 当前鉴权主体。
            raw: 上游返回的原始数据。

        Returns:
            含二维码与绑定字段的响应字典。
        """
        saved_bot_token = (binding.credentials or {}).get("bot_token")
        data = await call_weixin_clawbot_api(
            self._client().fetch_login_qrcode(
                local_token_list=[str(saved_bot_token)] if saved_bot_token else []
            )
        )
        qrcode = data.get("qrcode")
        qrcode_url = data.get("qrcode_img_content") or qrcode
        updated = await self.store.update_binding(
            binding.id,
            runtime_state={
                "status": "pending",
                "qrcode": qrcode,
                "qrcode_url": qrcode_url,
            },
        )
        await self.store.upsert_runtime_state(
            channel=WEIXIN_CLAWBOT_CHANNEL,
            state_key=weixin_binding_state_key(binding.id),
            data={
                "binding_id": binding.id,
                "owner_user_id": binding.owner_user_id,
                "manager_user_id": manager_user_id_from_actor(actor),
                "qrcode": qrcode,
                "qrcode_url": qrcode_url,
                "bot_token": saved_bot_token,
                "base_url": (binding.credentials or {}).get("base_url"),
            },
        )
        payload = updated.model_dump()
        payload["qrcode"] = (updated.runtime_state or {}).get("qrcode")
        payload["qrcode_url"] = (updated.runtime_state or {}).get("qrcode_url")
        if raw is not None:
            payload["raw"] = raw
        return payload

    async def create_qrcode(self, *, local_token_list: list[str]) -> dict[str, Any]:
        """请求上游生成登录二维码。

        Args:
            local_token_list: 客户端本地已保存的 token 列表。

        Returns:
            含二维码内容与原始数据的响应字典。
        """
        data = await call_weixin_clawbot_api(
            self._client().fetch_login_qrcode(local_token_list=local_token_list)
        )
        return {
            "qrcode": data.get("qrcode"),
            "qrcode_url": data.get("qrcode_img_content") or data.get("qrcode"),
            "raw": data,
        }

    async def get_qrcode_status(
        self,
        *,
        qrcode: str,
        verify_code: str | None = None,
    ) -> dict[str, Any]:
        """查询上游二维码扫码与登录状态。

        Args:
            qrcode: 二维码标识。
            verify_code: 可选的验证码。

        Returns:
            上游返回的状态字典。
        """
        return await call_weixin_clawbot_api(
            self._client().get_qrcode_status(qrcode=qrcode, verify_code=verify_code)
        )

    async def create_binding(
        self,
        *,
        actor: CurrentActor,
        owner_user_id: str,
        display_name: str,
    ) -> dict[str, Any]:
        """创建微信 ClawBot 绑定，刷新二维码并启动 runtime。

        Args:
            actor: 当前鉴权主体。
            owner_user_id: 绑定归属的用户 ID。
            display_name: 绑定展示名称。

        Returns:
            含二维码与绑定字段的响应字典。
        """
        ensure_binding_owner_or_manager_match(actor=actor, owner_user_id=owner_user_id)
        binding = await self.store.create_binding(
            channel=WEIXIN_CLAWBOT_CHANNEL,
            owner_user_id=owner_user_id,
            manager_user_id=manager_user_id_from_actor(actor),
            display_name=display_name,
            credentials={},
            runtime_state={"status": "pending"},
        )
        response = await self._binding_qrcode_response(binding=binding, actor=actor)
        await start_weixin_binding_runtime(binding_id=binding.id, store=self.store)
        return response

    async def refresh_binding_qrcode(
        self,
        *,
        actor: CurrentActor,
        binding_id: int,
    ) -> dict[str, Any]:
        """为指定绑定重新生成二维码并重启 runtime。

        Args:
            actor: 当前鉴权主体。
            binding_id: 渠道绑定 ID。

        Returns:
            含二维码与绑定字段的响应字典。
        """
        binding = await self._require_binding(actor=actor, binding_id=binding_id)
        await stop_weixin_binding_runtime(binding_id)
        response = await self._binding_qrcode_response(binding=binding, actor=actor)
        await start_weixin_binding_runtime(binding_id=binding_id, store=self.store)
        return response

    async def get_binding_qrcode_status(
        self,
        *,
        actor: CurrentActor,
        binding_id: int,
        verify_code: str | None = None,
    ) -> dict[str, Any]:
        """查询指定绑定的二维码状态并在确认后持久化凭据。

        Args:
            actor: 当前鉴权主体。
            binding_id: 渠道绑定 ID。
            verify_code: 可选的验证码。

        Returns:
            二维码状态字典。

        Raises:
            HTTPException: 绑定下没有可用二维码时抛出 404。
        """
        binding = await self._require_binding(actor=actor, binding_id=binding_id)
        state_key = weixin_binding_state_key(binding_id)
        runtime_state = await self.store.get_runtime_state(
            channel=WEIXIN_CLAWBOT_CHANNEL,
            state_key=state_key,
        )
        state_data = dict(runtime_state.data or {}) if runtime_state is not None else {}
        state_data.setdefault("qrcode", (binding.runtime_state or {}).get("qrcode"))
        state_data.setdefault("qrcode_url", (binding.runtime_state or {}).get("qrcode_url"))
        state_data.setdefault("bot_token", (binding.credentials or {}).get("bot_token"))
        state_data.setdefault("base_url", (binding.credentials or {}).get("base_url"))
        if state_data.get("bot_token"):
            base_url = str(state_data.get("base_url") or "").rstrip("/")
            return {
                "status": "confirmed",
                "bot_token": str(state_data["bot_token"]),
                "baseurl": base_url,
                "base_url": base_url,
                "qrcode": state_data.get("qrcode"),
                "qrcode_url": state_data.get("qrcode_url"),
            }

        login_qrcode = state_data.get("qrcode")
        if not login_qrcode:
            raise HTTPException(status_code=404, detail="Weixin ClawBot qrcode not found")

        status = await call_weixin_clawbot_api(
            self._client().get_qrcode_status(
                qrcode=str(login_qrcode),
                verify_code=verify_code,
            )
        )
        update_data = {
            "binding_id": binding_id,
            "owner_user_id": binding.owner_user_id,
            "manager_user_id": binding.manager_user_id,
            "qrcode": login_qrcode,
            "qrcode_url": state_data.get("qrcode_url"),
        }
        if status.get("bot_token"):
            update_data["bot_token"] = str(status["bot_token"])
        if status.get("baseurl"):
            update_data["base_url"] = str(status["baseurl"]).rstrip("/")
        await self.store.upsert_runtime_state(
            channel=WEIXIN_CLAWBOT_CHANNEL,
            state_key=state_key,
            data=update_data,
        )
        credentials: dict[str, str] = {}
        binding_runtime_state: dict[str, Any] = {
            "qrcode": login_qrcode,
            "qrcode_url": state_data.get("qrcode_url"),
        }
        if status.get("bot_token"):
            credentials["bot_token"] = str(status["bot_token"])
        if status.get("baseurl"):
            base_url = str(status["baseurl"]).rstrip("/")
            credentials["base_url"] = base_url
            binding_runtime_state["base_url"] = base_url
        await self.store.update_binding(
            binding_id,
            credentials=credentials,
            runtime_state=binding_runtime_state,
            status="active" if status.get("bot_token") else "pending",
        )
        if status.get("bot_token"):
            await start_weixin_binding_runtime(binding_id=binding_id, store=self.store)
        return status

    async def delete_binding(self, *, actor: CurrentActor, binding_id: int) -> bool:
        """停止 runtime 并删除指定微信 ClawBot 绑定及其运行态。

        Args:
            actor: 当前鉴权主体。
            binding_id: 渠道绑定 ID。

        Returns:
            是否删除成功。
        """
        await self._require_binding(actor=actor, binding_id=binding_id)
        await stop_weixin_binding_runtime(binding_id)
        await self.store.delete_runtime_state(
            channel=WEIXIN_CLAWBOT_CHANNEL,
            state_key=weixin_binding_state_key(binding_id),
        )
        return await self.store.delete_binding(binding_id)

    async def create_user_qrcode(self, *, actor: CurrentActor, user_id: str) -> dict[str, Any]:
        """按用户 ID 生成登录二维码，兼容旧调用路径。

        Args:
            actor: 当前鉴权主体。
            user_id: 绑定归属的用户 ID。

        Returns:
            含二维码内容与原始数据的响应字典。
        """
        ensure_binding_owner_or_manager_match(actor=actor, owner_user_id=user_id)
        state_key = weixin_clawbot_user_state_key(user_id)
        runtime_state = await self.store.get_runtime_state(
            channel=WEIXIN_CLAWBOT_CHANNEL,
            state_key=state_key,
        )
        if runtime_state is not None:
            ensure_runtime_state_access(
                actor=actor,
                state_key=state_key,
                state_data=runtime_state.data or {},
            )
        saved_bot_token = (
            runtime_state.data.get("bot_token")
            if runtime_state is not None and runtime_state.data
            else None
        )
        data = await call_weixin_clawbot_api(
            self._client().fetch_login_qrcode(
                local_token_list=[str(saved_bot_token)] if saved_bot_token else []
            )
        )
        qrcode = data.get("qrcode")
        qrcode_url = data.get("qrcode_img_content") or qrcode
        await self.store.upsert_runtime_state(
            channel=WEIXIN_CLAWBOT_CHANNEL,
            state_key=state_key,
            data={
                "owner_user_id": user_id,
                "manager_user_id": manager_user_id_from_actor(actor),
                "qrcode": qrcode,
                "qrcode_url": qrcode_url,
            },
        )
        await self.store.upsert_binding(
            channel=WEIXIN_CLAWBOT_CHANNEL,
            owner_user_id=user_id,
            manager_user_id=manager_user_id_from_actor(actor),
            display_name=f"Weixin ClawBot {user_id}",
            runtime_state={
                "qrcode": qrcode,
                "qrcode_url": qrcode_url,
            },
        )
        return {
            "qrcode": qrcode,
            "qrcode_url": qrcode_url,
            "raw": data,
        }

    async def get_user_qrcode_status(
        self,
        *,
        actor: CurrentActor,
        user_id: str,
        qrcode: str | None = None,
        verify_code: str | None = None,
    ) -> dict[str, Any]:
        """按用户 ID 查询二维码状态，兼容旧调用路径。

        Args:
            actor: 当前鉴权主体。
            user_id: 绑定归属的用户 ID。
            qrcode: 可选的二维码标识，缺省时取运行态中保存的值。
            verify_code: 可选的验证码。

        Returns:
            二维码状态字典。

        Raises:
            HTTPException: 没有可用二维码时抛出 404。
        """
        state_key = weixin_clawbot_user_state_key(user_id)
        runtime_state = await self.store.get_runtime_state(
            channel=WEIXIN_CLAWBOT_CHANNEL,
            state_key=state_key,
        )
        state_data = runtime_state.data if runtime_state is not None else {}
        if runtime_state is not None:
            ensure_runtime_state_access(
                actor=actor,
                state_key=state_key,
                state_data=state_data,
            )
        if state_data.get("bot_token"):
            base_url = str(state_data.get("base_url") or "").rstrip("/")
            return {
                "status": "confirmed",
                "bot_token": str(state_data["bot_token"]),
                "baseurl": base_url,
                "base_url": base_url,
                "qrcode": state_data.get("qrcode"),
                "qrcode_url": state_data.get("qrcode_url"),
            }

        login_qrcode = qrcode or state_data.get("qrcode")
        if not login_qrcode:
            raise HTTPException(status_code=404, detail="Weixin ClawBot qrcode not found")

        status = await call_weixin_clawbot_api(
            self._client().get_qrcode_status(
                qrcode=str(login_qrcode),
                verify_code=verify_code,
            )
        )
        update_data = {
            "owner_user_id": user_id,
            "manager_user_id": manager_user_id_from_actor(actor),
            "qrcode": login_qrcode,
        }
        if status.get("bot_token"):
            update_data["bot_token"] = str(status["bot_token"])
        if status.get("baseurl"):
            update_data["base_url"] = str(status["baseurl"]).rstrip("/")
        await self.store.upsert_runtime_state(
            channel=WEIXIN_CLAWBOT_CHANNEL,
            state_key=state_key,
            data=update_data,
        )
        binding_runtime_state: dict[str, Any] = {"qrcode": login_qrcode}
        credentials: dict[str, str] = {}
        if status.get("bot_token"):
            credentials["bot_token"] = str(status["bot_token"])
        if status.get("baseurl"):
            base_url = str(status["baseurl"]).rstrip("/")
            credentials["base_url"] = base_url
            binding_runtime_state["base_url"] = base_url
        await self.store.upsert_binding(
            channel=WEIXIN_CLAWBOT_CHANNEL,
            owner_user_id=user_id,
            manager_user_id=manager_user_id_from_actor(actor),
            display_name=f"Weixin ClawBot {user_id}",
            credentials=credentials,
            runtime_state=binding_runtime_state,
        )
        if status.get("bot_token"):
            await start_weixin_clawbot_runtime(
                state_key=state_key,
                store=self.store,
                qrcode=str(login_qrcode),
            )
        return status

    async def list_users(self, *, actor: CurrentActor) -> WeixinClawBotBoundUserList:
        """返回当前用户或管理员可见范围内的微信 ClawBot 运行态。

        Args:
            actor: 当前鉴权主体。

        Returns:
            已绑定用户列表响应。
        """
        states = await self.store.list_runtime_states(channel=WEIXIN_CLAWBOT_CHANNEL)
        current_manager_user_id = accessible_binding_user_id(actor)
        items: list[WeixinClawBotBoundUserRead] = []
        for state in states:
            state_user_id = weixin_clawbot_user_id_from_state_key(state.state_key)
            if state_user_id is None:
                continue

            state_data = state.data or {}
            if (
                current_manager_user_id is not None
                and runtime_state_manager_user_id(state_data, state.state_key)
                != current_manager_user_id
            ):
                continue
            user_id = str(state_data.get("owner_user_id") or state_user_id)
            bot_token = state_data.get("bot_token")
            connected = bool(bot_token)
            items.append(
                WeixinClawBotBoundUserRead(
                    user_id=user_id,
                    state_key=state.state_key,
                    connected=connected,
                    status="connected" if connected else "pending",
                    bot_token=mask_token(str(bot_token)) if bot_token else None,
                    qrcode_url=state_data.get("qrcode_url"),
                    base_url=state_data.get("base_url"),
                    updated_at=state.updated_at.isoformat(),
                )
            )

        return WeixinClawBotBoundUserList(items=items, total=len(items))

    async def delete_user(self, *, actor: CurrentActor, user_id: str) -> bool:
        """按用户 ID 删除微信 ClawBot 运行态，兼容旧调用路径。

        Args:
            actor: 当前鉴权主体。
            user_id: 绑定归属的用户 ID。

        Returns:
            是否删除成功。

        Raises:
            HTTPException: 用户运行态不存在时抛出 404。
        """
        state_key = weixin_clawbot_user_state_key(user_id)
        runtime_state = await self.store.get_runtime_state(
            channel=WEIXIN_CLAWBOT_CHANNEL,
            state_key=state_key,
        )
        if runtime_state is None:
            raise HTTPException(status_code=404, detail="Weixin ClawBot user not found")
        ensure_runtime_state_access(
            actor=actor,
            state_key=state_key,
            state_data=runtime_state.data or {},
        )

        await stop_weixin_clawbot_runtime(state_key)
        return await self.store.delete_runtime_state(
            channel=WEIXIN_CLAWBOT_CHANNEL,
            state_key=state_key,
        )

    async def fetch_pending_messages(
        self,
        *,
        bot_token: str,
        get_updates_buf: str,
    ) -> tuple[WeixinClawBotAdapter, list[ChannelMessage], str]:
        """拉取并解析微信 ClawBot 待处理消息。

        Args:
            bot_token: 机器人访问令牌。
            get_updates_buf: 上次拉取返回的游标。

        Returns:
            解析用的适配器、消息列表与下一次拉取使用的游标。
        """
        client = self._client()
        adapter = WeixinClawBotAdapter(token=bot_token, client=client)
        updates = await call_weixin_clawbot_api(
            client.get_updates(
                token=bot_token,
                get_updates_buf=get_updates_buf,
            )
        )
        messages = adapter.iter_text_messages(updates)
        next_buf = updates.get("get_updates_buf") or get_updates_buf
        return adapter, messages, next_buf

    async def process_message(
        self,
        message: ChannelMessage,
        adapter: WeixinClawBotAdapter,
    ) -> None:
        """将渠道消息交给共享的渠道服务处理。

        Args:
            message: 待处理的渠道消息。
            adapter: 对应的渠道适配器。

        Returns:
            无。
        """
        await self.channel_service.process_message(message, adapter)
