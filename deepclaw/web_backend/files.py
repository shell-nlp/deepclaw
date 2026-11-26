"""聊天文件的 HTTP 上传和下载。"""

import asyncio
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Response, UploadFile
from pydantic import BaseModel, Field, StrictBool

from deepclaw.middleware.files.query import inspect_document, read_lines
from deepclaw.middleware.files.service import MAX_BYTES, MIME_TYPES, file_details, get_file_service
from deepclaw.web_backend.auth.dependencies import CurrentActor
from deepclaw.web_backend.auth.rbac.dependencies import require_permission
from deepclaw.web_backend.common.file_upload import FileFingerprint

router = APIRouter(prefix="/api/files", tags=["files"])


class ChatFileResponse(BaseModel):
    """上传后可在聊天消息中引用的文件。"""

    file_id: str
    name: str
    extension: str
    size: int
    created_at: str
    favorite: bool
    download_url: str


class ChatFileListResponse(BaseModel):
    """文件知识库的分页列表。"""

    files: list[ChatFileResponse]
    next_offset: int | None


class ChatFileUploadResponse(ChatFileResponse):
    """标明上传是否复用了已有记录。"""

    reused: bool


@router.post("/upload-check", response_model=ChatFileUploadResponse | None)
async def check_upload(
    body: FileFingerprint,
    actor: CurrentActor = Depends(require_permission("/api/files", "write")),
):
    """仅在当前账号内预查可复用的文件。"""
    if body.extension not in MIME_TYPES or body.size > MAX_BYTES:
        return None
    record = await get_file_service().find_upload(actor.user_id, body.extension, body.size, body.sha256)
    return {**file_details(record), "reused": True} if record else None


class FavoriteFileRequest(BaseModel):
    """文件应移动到的列表。"""

    favorite: StrictBool


class FileRetentionRequest(BaseModel):
    """自动清理设置，空值表示关闭。"""

    retention_days: int | None = Field(ge=1, le=3650)


class FileRetentionResponse(BaseModel):
    """当前账号的自动清理设置。"""

    retention_days: int | None


@router.get("", response_model=ChatFileListResponse)
async def list_files(
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=50),
    favorite: bool = False,
    actor: CurrentActor = Depends(require_permission("/api/files", "read")),
):
    """分页列出当前账号的文件。

    Args:
        offset: 跳过的记录数量。
        limit: 当前页最大数量。
        favorite: 收藏区为真，全部区为假。
        actor: 有读取权限的登录账号。
    """
    records = await get_file_service().list(actor.user_id, offset, limit + 1, favorite)
    return {
        "files": [file_details(record) for record in records[:limit]],
        "next_offset": offset + limit if len(records) > limit else None,
    }


@router.get("/retention", response_model=FileRetentionResponse)
async def get_retention(actor: CurrentActor = Depends(require_permission("/api/files", "read"))):
    """读取当前账号的自动清理设置。

    Args:
        actor: 有读取权限的登录账号。
    """
    return {"retention_days": await get_file_service().get_retention(actor.user_id)}


@router.put("/retention", response_model=FileRetentionResponse)
async def set_retention(
    body: FileRetentionRequest,
    actor: CurrentActor = Depends(require_permission("/api/files", "write")),
):
    """保存当前账号的自动清理设置。

    Args:
        body: 保留天数设置。
        actor: 有写入权限的登录账号。
    """
    await get_file_service().set_retention(actor.user_id, body.retention_days)
    return {"retention_days": body.retention_days}


@router.put("/{file_id}/favorite", response_model=ChatFileResponse)
async def set_favorite(
    file_id: str,
    body: FavoriteFileRequest,
    actor: CurrentActor = Depends(require_permission("/api/files", "write")),
):
    """将本人文件移动到全部或收藏区。

    Args:
        file_id: 文件 ID。
        body: 目标收藏状态。
        actor: 有写入权限的登录账号。
    """
    try:
        return file_details(await get_file_service().set_favorite(actor.user_id, file_id, body.favorite))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="找不到文件。") from exc


@router.delete("/{file_id}", status_code=204)
async def delete_file(file_id: str, actor: CurrentActor = Depends(require_permission("/api/files", "write"))):
    """删除当前账号的文件及其解析缓存。

    Args:
        file_id: 文件 ID。
        actor: 有写入权限的登录账号。
    """
    try:
        await get_file_service().remove(actor.user_id, file_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="找不到文件。") from exc


@router.get("/{file_id}/preview")
async def preview_file(
    file_id: str,
    sheet: str | None = None,
    start_line: int = Query(1, ge=1),
    limit: int = Query(100, ge=1, le=200),
    actor: CurrentActor = Depends(require_permission("/api/files", "read")),
):
    """按行预览文件并返回工作表或页码信息。

    Args:
        file_id: 文件 ID。
        sheet: Excel 工作表名称。
        start_line: 起始行号。
        limit: 最多返回的行数。
        actor: 有读取权限的登录账号。
    """
    service = get_file_service()
    try:
        record = await service.get(actor.user_id, file_id)
        document = await service.parsed(record)
        result = await asyncio.to_thread(read_lines, document, sheet, start_line, limit, None)
    except (LookupError, FileNotFoundError) as exc:
        raise HTTPException(status_code=404, detail="找不到文件。") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {**inspect_document(document), **result}


@router.post("", response_model=ChatFileUploadResponse, status_code=201)
async def upload_file(
    file: UploadFile, response: Response,
    actor: CurrentActor = Depends(require_permission("/api/files", "write")),
):
    """上传并保存当前登录账号的文件。

    Args:
        file: 上传的文件。
        actor: 有写入权限的登录账号。
    """
    try:
        data = await file.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            raise HTTPException(status_code=413, detail="文件大小不能超过 20 MiB。")
        record, reused = await get_file_service().upload(actor.user_id, file.filename or "", data)
        if reused:
            response.status_code = 200
        return {**file_details(record), "reused": reused}
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    finally:
        await file.close()


@router.get("/{file_id}/download")
async def download_file(file_id: str, actor: CurrentActor = Depends(require_permission("/api/files", "read"))):
    """下载当前账号的原始文件或生成件。

    Args:
        file_id: 文件 ID。
        actor: 有读取权限的登录账号。
    """
    service = get_file_service()
    try:
        record = await service.get(actor.user_id, file_id)
        data = await service.download(record)
    except (LookupError, FileNotFoundError) as exc:
        raise HTTPException(status_code=404, detail="找不到文件。") from exc
    return Response(data, media_type=MIME_TYPES[record.extension], headers={
        "Content-Disposition": f"attachment; filename*=UTF-8''{quote(record.name, safe='')}",
        "Cache-Control": "private, no-store",
        "X-Content-Type-Options": "nosniff",
    })
