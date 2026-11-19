from pathlib import Path

from deepclaw.web_backend.auth.rbac.store import RbacPolicyStore


async def bootstrap_policy_store(
    store: RbacPolicyStore,
    policies: list[tuple[str, str, str]],
    roles: list[tuple[str, str]],
) -> None:
    """建表并在空库写入基础策略。

    Args:
        store: 策略存储。
        policies: 基础策略三元组。
        roles: 基础角色继承二元组。
    """
    await store.ensure_schema()
    if not await store.is_initialized():
        await store.seed(policies, roles)
        return
    # 已有安装也要补齐新版本新增的基础策略，不覆盖管理员在界面里的自定义策略。
    for subject, path, action in policies:
        await store.add_policy(subject, path, action)
    for child, parent in roles:
        await store.add_role(child, parent)


def read_default_policy_file(policy_path: Path) -> tuple[list[tuple[str, str, str]], list[tuple[str, str]]]:
    """解析默认 policy.csv，得到策略与角色列表。

    Args:
        policy_path: policy.csv 路径。

    Returns:
        tuple[list[tuple[str, str, str]], list[tuple[str, str]]]: 策略三元组与角色继承二元组。
    """
    policies: list[tuple[str, str, str]] = []
    roles: list[tuple[str, str]] = []
    for raw_line in policy_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        parts = [item.strip() for item in line.split(",")]
        if parts[0] == "p" and len(parts) >= 4:
            policies.append((parts[1], parts[2], parts[3]))
        elif parts[0] == "g" and len(parts) >= 3:
            roles.append((parts[1], parts[2]))
    return policies, roles
