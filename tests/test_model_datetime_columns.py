from sqlalchemy import DateTime

from deepclaw.middleware.cron.cron_manager import CronJob
from deepclaw.web_backend.agent.run_store import (
    AgUiRunEventRecord,
    AgUiRunRecord,
    AgUiThreadRecord,
)
from deepclaw.web_backend.auth.models import AccessTokenRecord, AuthUser
from deepclaw.web_backend.auth.rbac.models import RbacPolicyRule, RbacRoleRule
from deepclaw.web_backend.channels.models import ChannelBinding, ChannelUser

DATETIME_COLUMNS = [
    (AuthUser, "created_at"),
    (AuthUser, "updated_at"),
    (AccessTokenRecord, "expires_at"),
    (AccessTokenRecord, "last_used_at"),
    (AccessTokenRecord, "created_at"),
    (RbacPolicyRule, "created_at"),
    (RbacRoleRule, "created_at"),
    (ChannelUser, "created_at"),
    (ChannelBinding, "updated_at"),
    (AgUiRunRecord, "expires_at"),
    (AgUiRunEventRecord, "expires_at"),
    (AgUiThreadRecord, "expires_at"),
    (CronJob, "created_at"),
]


def test_datetime_columns_store_naive_utc():
    """验证时间列显式使用无时区 DateTime。

    SQLModel 0.0.50 起把 datetime 列映射为带时区的 UTCDateTime，并按无时区值报错；
    项目仍统一按无时区 UTC 存储，因此必须显式传 sa_type=DateTime。
    """

    for model, attribute in DATETIME_COLUMNS:
        column = model.__table__.columns[attribute]
        assert type(column.type) is DateTime, (
            f"{model.__name__}.{attribute} 必须显式声明 sa_type=DateTime"
        )
        assert column.type.timezone is False
