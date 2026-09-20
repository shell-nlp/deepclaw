from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from deepclaw.web_backend.auth.dependencies import get_current_actor
from deepclaw.web_backend.skills.schemas import (
    SkillDeleteRequest,
    SkillListRequest,
)
from deepclaw.web_backend.skills.service import (
    SkillDeleteResponse,
    SkillListResponse,
    SkillUploadResponse,
    skill_manager,
)


def _handle_value_error(exc: ValueError) -> HTTPException:
    return HTTPException(status_code=400, detail=str(exc))


def add_skill_management_routes(
    router: APIRouter, tags: list[str] | None = None
) -> None:
    @router.post("/skills/list", response_model=SkillListResponse, tags=tags, summary="查询技能列表", description="返回当前可用的技能包及其元数据。")
    def list_skills(request: SkillListRequest, actor=Depends(get_current_actor)):
        try:
            return skill_manager.list_skills(search=request.search)
        except ValueError as exc:
            raise _handle_value_error(exc) from exc

    @router.post("/skills/upload", response_model=SkillUploadResponse, tags=tags, summary="上传技能", description="上传技能包文件并保存到服务端技能目录。")
    async def upload_skill(
        file: UploadFile = File(..., description="Skill zip package"),
        actor=Depends(get_current_actor),
    ):
        if actor.is_guest:
            raise HTTPException(status_code=403, detail="登录后可上传技能。")
        data = await file.read()
        await file.close()
        try:
            return skill_manager.upload_skill_zip(
                file_name=file.filename or "skill.zip",
                data=data,
            )
        except ValueError as exc:
            raise _handle_value_error(exc) from exc

    @router.post("/skills/delete", response_model=SkillDeleteResponse, tags=tags, summary="删除技能", description="删除指定技能包及其关联文件。")
    def delete_skill(
        request: SkillDeleteRequest,
        actor=Depends(get_current_actor),
    ):
        if actor.is_guest:
            raise HTTPException(status_code=403, detail="登录后可删除技能。")
        try:
            return skill_manager.delete_skill(skill_name=request.skill_name)
        except ValueError as exc:
            raise _handle_value_error(exc) from exc


def create_skills_router() -> APIRouter:
    router = APIRouter(prefix="/api/agent")
    add_skill_management_routes(router, tags=["agent-skills"])
    return router


