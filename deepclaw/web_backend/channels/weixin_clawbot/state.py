from typing import Any


RUNTIME_STATE_KEY = "default"
DEFAULT_MANAGER_USER_ID = "guest"


def weixin_clawbot_user_state_key(user_id: str) -> str:
    return f"user:{user_id}"


def weixin_clawbot_user_id_from_state_key(state_key: str) -> str | None:
    if not state_key.startswith("user:"):
        return None
    user_id = state_key.removeprefix("user:")
    return user_id or None


def weixin_clawbot_manager_user_id_from_state(
    state_key: str,
    state: dict[str, Any],
) -> str | None:
    manager_user_id = state.get("manager_user_id")
    if manager_user_id:
        return str(manager_user_id)

    owner_user_id = state.get("owner_user_id")
    if owner_user_id:
        return str(owner_user_id)

    return weixin_clawbot_user_id_from_state_key(state_key)


def runtime_state_manager_user_id(state_data: dict[str, Any], state_key: str) -> str:
    manager_user_id = state_data.get("manager_user_id")
    if manager_user_id:
        return str(manager_user_id)

    owner_user_id = state_data.get("owner_user_id")
    if owner_user_id:
        return str(owner_user_id)

    return (
        weixin_clawbot_user_id_from_state_key(state_key)
        or DEFAULT_MANAGER_USER_ID
    )


def mask_token(value: str | None) -> str | None:
    if not value:
        return None
    if len(value) <= 5:
        return "***"
    return f"{value[:5]}...{value[-3:]}"
