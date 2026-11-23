from datetime import UTC, datetime

from sqlalchemy import DateTime
from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    """返回不带时区的 UTC 当前时间。

    Args:
        无。

    Returns:
        datetime: UTC 当前时间。
    """
    return datetime.now(UTC).replace(tzinfo=None)


class RbacCatalogRole(SQLModel, table=True):
    """可管理的角色目录实体。

    Args:
        id: 稳定角色标识，同时作为 Casbin 策略主体。
        name: 可显示的角色名称。
        description: 角色说明。
    """

    __tablename__ = "rbac_catalog_roles"

    id: str = Field(primary_key=True, max_length=128)
    name: str = Field(max_length=128)
    description: str = Field(default="", max_length=512)


class RbacPolicyRule(SQLModel, table=True):
    """Casbin 策略行，与 policy.csv 的一行对应。

    Args:
        id: 自增主键。
        subject: 策略主体，角色名或用户 ID。
        path: 资源路径，按 keyMatch 规则匹配。
        action: 动作名称，例如 read 或 write。
        created_at: 创建时间。
    """

    __tablename__ = "rbac_policy_rules"

    id: int | None = Field(default=None, primary_key=True)
    subject: str = Field(index=True)
    path: str = Field(index=True)
    action: str = Field(index=True)
    created_at: datetime = Field(default_factory=utc_now, sa_type=DateTime)


class RbacRoleRule(SQLModel, table=True):
    """Casbin 角色继承行，对应 g 规则。

    Args:
        id: 自增主键。
        child: 子角色或被赋予角色的用户 ID。
        parent: 父角色。
        created_at: 创建时间。
    """

    __tablename__ = "rbac_role_rules"

    id: int | None = Field(default=None, primary_key=True)
    child: str = Field(index=True)
    parent: str = Field(index=True)
    created_at: datetime = Field(default_factory=utc_now, sa_type=DateTime)
