from pydantic import BaseModel, Field


class SkillListRequest(BaseModel):
    search: str = Field("", description="Search text")


class SkillDeleteRequest(BaseModel):
    skill_name: str = Field(..., description="Skill name")
