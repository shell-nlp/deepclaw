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


router = APIRouter(prefix="/api/agent", tags=["agent-skills"])


@router.post("/skills/list", response_model=SkillListResponse, summary="查询技能列表", description="返回当前可用的技能包及其元数据。")
def list_skills(request: SkillListRequest, actor=Depends(get_current_actor)):
    """查询技能包列表。"""
    return skill_manager.list_skills(search=request.search)


@router.post("/skills/upload", response_model=SkillUploadResponse, summary="上传技能", description="上传技能包文件并保存到服务端技能目录。")
async def upload_skill(
    file: UploadFile = File(..., description="Skill zip package"),
    actor=Depends(get_current_actor),
):
    """上传技能包压缩文件。"""
    if actor.is_guest:
        raise HTTPException(status_code=403, detail="登录后可上传技能。")
    data = await file.read()
    await file.close()
    return skill_manager.upload_skill_zip(
        file_name=file.filename or "skill.zip",
        data=data,
    )


@router.post("/skills/delete", response_model=SkillDeleteResponse, summary="删除技能", description="删除指定技能包及其关联文件。")
def delete_skill(
    request: SkillDeleteRequest,
    actor=Depends(get_current_actor),
):
    """删除指定技能包。"""
    if actor.is_guest:
        raise HTTPException(status_code=403, detail="登录后可删除技能。")
    return skill_manager.delete_skill(skill_name=request.skill_name)


def add_skill_management_routes(target_router: APIRouter) -> None:
    """把模块级技能路由加入目标路由器。"""
    target_router.include_router(router)


def create_skills_router() -> APIRouter:
    """返回模块级技能路由器。"""
    return router
