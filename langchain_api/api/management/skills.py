from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from langchain_api.agent.skill_manager import (
    SkillDeleteResponse,
    SkillListResponse,
    SkillUploadResponse,
    skill_manager,
)


class SkillListRequest(BaseModel):
    search: str = Field("", description="Search text")


class SkillDeleteRequest(BaseModel):
    skill_name: str = Field(..., description="Skill name")


def _handle_value_error(exc: ValueError) -> HTTPException:
    return HTTPException(status_code=400, detail=str(exc))


def add_skill_management_routes(
    router: APIRouter, tags: list[str] | None = None
) -> None:
    @router.post("/skills/list", response_model=SkillListResponse, tags=tags)
    def list_skills(request: SkillListRequest):
        try:
            return skill_manager.list_skills(search=request.search)
        except ValueError as exc:
            raise _handle_value_error(exc) from exc

    @router.post("/skills/upload", response_model=SkillUploadResponse, tags=tags)
    async def upload_skill(file: UploadFile = File(..., description="Skill zip package")):
        data = await file.read()
        await file.close()
        try:
            return skill_manager.upload_skill_zip(
                file_name=file.filename or "skill.zip",
                data=data,
            )
        except ValueError as exc:
            raise _handle_value_error(exc) from exc

    @router.post("/skills/delete", response_model=SkillDeleteResponse, tags=tags)
    def delete_skill(request: SkillDeleteRequest):
        try:
            return skill_manager.delete_skill(skill_name=request.skill_name)
        except ValueError as exc:
            raise _handle_value_error(exc) from exc
