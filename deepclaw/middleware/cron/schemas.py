from datetime import UTC, datetime
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from croniter import croniter
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_serializer, model_validator

OutputFormat = Literal["notification", "md", "docx"]
TaskMode = Literal["literal", "generate"]


class ScheduleRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    content: str = Field(min_length=1, max_length=16000)
    timezone: str = Field(default="Asia/Shanghai", max_length=80)
    cron: str | None = Field(default=None, max_length=120)
    interval_seconds: int | None = Field(default=None, ge=1)
    run_at: AwareDatetime | None = None
    mode: TaskMode = "literal"
    output: OutputFormat = "notification"
    enabled: bool = True

    @model_validator(mode="after")
    def validate_schedule(self):
        """校验任务时区和调度表达式。

        Args:
            无。
        """
        try:
            ZoneInfo(self.timezone)
        except (ValueError, ZoneInfoNotFoundError) as exc:
            raise ValueError("请输入有效的 IANA 时区，例如 Asia/Shanghai。") from exc
        triggers = (self.cron, self.run_at, self.interval_seconds)
        if sum(value is not None for value in triggers) != 1:
            raise ValueError("请选择一次性执行、按秒间隔执行或 Cron 周期执行。")
        if self.cron is not None and (
            len(self.cron.split()) not in (5, 6)
            or not croniter.is_valid(self.cron, second_at_beginning=True)
        ):
            raise ValueError("Cron 支持五段「分 时 日 月 周」和六段「秒 分 时 日 月 周」。")
        return self

    @field_serializer("run_at")
    def serialize_run_at(self, value: datetime | None):
        """将一次性触发时间序列化为 UTC。

        Args:
            value: 一次性触发时间。
        """
        return value.astimezone(UTC).isoformat() if value else None


class ScheduleResponse(BaseModel):
    id: str
    settings: ScheduleRequest
    next_at: AwareDatetime | None


class ScheduleRunResponse(BaseModel):
    id: str
    job_id: str
    name: str
    status: Literal["running", "succeeded", "failed"]
    scheduled_at: AwareDatetime
    finished_at: AwareDatetime | None
    read_at: AwareDatetime | None
    message: str | None
    filename: str | None


class NotificationsResponse(BaseModel):
    items: list[ScheduleRunResponse]
    unread: int

