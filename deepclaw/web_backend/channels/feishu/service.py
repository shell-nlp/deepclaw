from typing import Any

from deepclaw.web_backend.auth.dependencies import CurrentActor
from deepclaw.web_backend.channels.common import (
    ensure_binding_access,
    ensure_binding_owner_or_manager_match,
    is_admin,
    manager_user_id_from_actor,
)
from deepclaw.web_backend.channels.feishu.runtime import (
    start_feishu_runtime,
    stop_feishu_runtime,
)
from deepclaw.web_backend.channels.feishu.schemas import FeishuBindingRequest
from deepclaw.web_backend.channels.models import ChannelBinding
from deepclaw.web_backend.channels.store import ChannelStore, get_channel_store


class FeishuBindingService:
    """飞书渠道绑定编排服务。"""

    def __init__(self, *, store: ChannelStore | None = None) -> None:
        self.store = store or get_channel_store()

    def _binding_fields(self, request: FeishuBindingRequest) -> dict[str, Any]:
        """从请求中提取飞书绑定需要的凭据与配置。

        Args:
            request: 飞书绑定创建或更新请求。

        Returns:
            包含 credentials 与 config 两个键的字典。
        """
        return {
            "credentials": {
                "app_id": request.app_id,
                "app_secret": request.app_secret,
            },
            "config": {
                "domain": request.domain,
                "group_policy": request.group_policy,
                "streaming": request.streaming,
                "react_emoji": request.react_emoji,
                "done_emoji": request.done_emoji,
            },
        }

    async def upsert_binding_for_user(
        self,
        *,
        actor: CurrentActor,
        user_id: str,
        request: FeishuBindingRequest,
    ) -> ChannelBinding:
        """按用户 ID 创建或更新飞书绑定并启动长连接 runtime。

        Args:
            actor: 当前鉴权主体。
            user_id: 绑定归属的用户 ID。
            request: 飞书绑定创建或更新请求。

        Returns:
            创建或更新后的渠道绑定。
        """
        ensure_binding_owner_or_manager_match(actor=actor, owner_user_id=user_id)
        fields = self._binding_fields(request)
        binding = await self.store.upsert_binding(
            channel="feishu",
            owner_user_id=user_id,
            manager_user_id=manager_user_id_from_actor(actor),
            display_name=request.display_name or f"Feishu {user_id}",
            credentials=fields["credentials"],
            config=fields["config"],
            runtime_state={"status": "starting"},
        )
        await start_feishu_runtime(binding_id=binding.id, store=self.store)
        return binding

    async def create_binding(
        self,
        *,
        actor: CurrentActor,
        request: FeishuBindingRequest,
    ) -> ChannelBinding:
        """为指定归属用户新建飞书绑定并启动长连接 runtime。

        Args:
            actor: 当前鉴权主体。
            request: 飞书绑定创建请求。

        Returns:
            新建后的渠道绑定。
        """
        owner_user_id = request.owner_user_id or manager_user_id_from_actor(actor)
        ensure_binding_owner_or_manager_match(actor=actor, owner_user_id=owner_user_id)
        fields = self._binding_fields(request)
        binding = await self.store.create_binding(
            channel="feishu",
            owner_user_id=owner_user_id,
            manager_user_id=manager_user_id_from_actor(actor),
            display_name=request.display_name or f"Feishu {owner_user_id}",
            credentials=fields["credentials"],
            config=fields["config"],
            runtime_state={"status": "starting"},
        )
        await start_feishu_runtime(binding_id=binding.id, store=self.store)
        return binding

    async def list_bindings(self, *, actor: CurrentActor) -> list[ChannelBinding]:
        """返回当前用户或管理员可见范围内的飞书绑定。

        Args:
            actor: 当前鉴权主体。

        Returns:
            可见的飞书绑定列表。
        """
        return await self.store.list_bindings(
            channel="feishu",
            participant_user_id=(
                None if is_admin(actor) else manager_user_id_from_actor(actor)
            ),
        )

    async def get_binding_for_user(
        self,
        *,
        actor: CurrentActor,
        user_id: str,
    ) -> ChannelBinding:
        """返回指定用户当前使用的飞书绑定。

        Args:
            actor: 当前鉴权主体。
            user_id: 绑定归属的用户 ID。

        Returns:
            该用户的首个飞书绑定。

        Raises:
            HTTPException: 绑定不存在或当前用户无权访问时抛出 404。
        """
        bindings = await self.store.list_bindings(channel="feishu", owner_user_id=user_id)
        binding = bindings[0] if bindings else None
        ensure_binding_access(
            actor=actor,
            binding=binding,
            not_found_detail="Feishu binding not found",
        )
        return binding

    async def delete_binding_for_user(
        self,
        *,
        actor: CurrentActor,
        user_id: str,
    ) -> bool:
        """停止 runtime 并删除指定用户的飞书绑定。

        Args:
            actor: 当前鉴权主体。
            user_id: 绑定归属的用户 ID。

        Returns:
            是否删除成功。
        """
        binding = await self.get_binding_for_user(actor=actor, user_id=user_id)
        await stop_feishu_runtime(binding.id)
        return await self.store.delete_binding(binding.id)

    async def delete_binding(
        self,
        *,
        actor: CurrentActor,
        binding_id: int,
    ) -> bool:
        """停止 runtime 并按绑定 ID 删除飞书绑定。

        Args:
            actor: 当前鉴权主体。
            binding_id: 渠道绑定 ID。

        Returns:
            是否删除成功。
        """
        binding = await self.store.get_binding(binding_id)
        ensure_binding_access(
            actor=actor,
            binding=binding,
            not_found_detail="Feishu binding not found",
        )
        await stop_feishu_runtime(binding_id)
        return await self.store.delete_binding(binding_id)
