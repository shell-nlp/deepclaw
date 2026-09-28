from fastapi import APIRouter, Depends, File, Form, UploadFile, status

from deepclaw.web_backend.auth.dependencies import get_current_actor
from deepclaw.web_backend.knowledge_bases.schemas import (
    BulkDeleteKnowledgeBaseDocumentRequest,
    BulkDeleteKnowledgeBaseRequest,
    CreateKnowledgeBaseRequest,
    DeleteKnowledgeBaseDocumentRequest,
    DocumentDetailRequest,
    DocumentListRequest,
    KnowledgeBaseIdentityRequest,
    KnowledgeUploadTaskRequest,
    KnowledgeBaseListRequest,
    UpdateKnowledgeChunkRequest,
    UpdateKnowledgeBaseDocumentRequest,
    UpdateKnowledgeBaseRequest,
)
from deepclaw.web_backend.knowledge_bases.service import (
    BulkDeleteDocumentResponse,
    BulkDeleteKnowledgeBaseResponse,
    KnowledgeBaseDeleteResult,
    KnowledgeBaseDocumentChunkRecord,
    KnowledgeBaseDocumentDetailResponse,
    KnowledgeBaseDocumentRecord,
    KnowledgeBaseRecord,
    KnowledgeUploadTaskDeleteResponse,
    KnowledgeUploadSubmissionResponse,
    KnowledgeUploadTaskResponse,
    PaginatedKnowledgeBaseDocumentResponse,
    PaginatedKnowledgeBaseResponse,
    UploadedKnowledgeFile,
    get_knowledge_base_manager,
)


def _resolved_user_id(actor) -> str:
    """解析知识库归属用户 ID，游客统一落到 guest 身份。

    Args:
        actor: 当前鉴权主体。
    """
    return actor.user_id if actor.user_id and not actor.is_guest else "guest"


router = APIRouter(prefix="/api/rag", tags=["rag-knowledge-bases"])

@router.post(
    "/knowledge-bases/list",
    response_model=PaginatedKnowledgeBaseResponse,
    summary="查询知识库列表",
    description="分页查询当前用户可访问的知识库。"
)
async def list_knowledge_bases(
    request: KnowledgeBaseListRequest,
    actor=Depends(get_current_actor),
):
    return await get_knowledge_base_manager().search_knowledge_bases(
        user_id=_resolved_user_id(actor),
        search=request.search,
        page=request.page,
        page_size=request.page_size,
    )

@router.post("/knowledge-bases/create", response_model=KnowledgeBaseRecord, summary="创建知识库", description="创建知识库元数据并初始化对应的检索索引。")
async def create_knowledge_base(
    request: CreateKnowledgeBaseRequest,
    actor=Depends(get_current_actor),
):
    owner_id = _resolved_user_id(actor)
    return await get_knowledge_base_manager().create_knowledge_base(
        user_id=owner_id,
        name=request.name,
        description=request.description,
    )

@router.post("/knowledge-bases/detail", response_model=KnowledgeBaseRecord, summary="获取知识库详情", description="返回指定知识库的元数据、文档统计和索引信息。")
async def get_knowledge_base(
    request: KnowledgeBaseIdentityRequest,
    actor=Depends(get_current_actor),
):
    return await get_knowledge_base_manager().get_knowledge_base(
        user_id=_resolved_user_id(actor),
        knowledge_base_id=request.knowledge_base_id,
    )

@router.post("/knowledge-bases/update", response_model=KnowledgeBaseRecord, summary="更新知识库", description="修改知识库名称、描述等元数据。")
async def update_knowledge_base(
    request: UpdateKnowledgeBaseRequest,
    actor=Depends(get_current_actor),
):
    owner_id = _resolved_user_id(actor)
    return await get_knowledge_base_manager().update_knowledge_base(
        user_id=owner_id,
        knowledge_base_id=request.knowledge_base_id,
        name=request.name,
        description=request.description,
    )

@router.post("/knowledge-bases/delete", response_model=KnowledgeBaseDeleteResult, summary="删除知识库", description="删除指定知识库及其关联索引和文档元数据。")
async def delete_knowledge_base(
    request: KnowledgeBaseIdentityRequest,
    actor=Depends(get_current_actor),
):
    owner_id = _resolved_user_id(actor)
    return await get_knowledge_base_manager().delete_knowledge_base(
        user_id=owner_id,
        knowledge_base_id=request.knowledge_base_id,
    )

@router.post(
    "/knowledge-bases/bulk-delete",
    response_model=BulkDeleteKnowledgeBaseResponse,
    summary="批量删除知识库",
    description="批量删除多个知识库及其关联数据。"
)
async def bulk_delete_knowledge_bases(
    request: BulkDeleteKnowledgeBaseRequest,
    actor=Depends(get_current_actor),
):
    owner_id = _resolved_user_id(actor)
    return await get_knowledge_base_manager().bulk_delete_knowledge_bases(
        user_id=owner_id,
        knowledge_base_ids=request.knowledge_base_ids,
    )

@router.post(
    "/knowledge-bases/documents/list",
    response_model=PaginatedKnowledgeBaseDocumentResponse,
    summary="查询文档列表",
    description="分页查询指定知识库中的文档。"
)
async def list_documents(
    request: DocumentListRequest,
    actor=Depends(get_current_actor),
):
    return await get_knowledge_base_manager().search_documents(
        user_id=_resolved_user_id(actor),
        knowledge_base_id=request.knowledge_base_id,
        search=request.search,
        page=request.page,
        page_size=request.page_size,
    )

@router.post(
    "/knowledge-bases/documents/detail",
    response_model=KnowledgeBaseDocumentDetailResponse,
    summary="获取文档详情",
    description="返回文档元数据、切片内容和索引状态。"
)
async def get_document_detail(
    request: DocumentDetailRequest,
    actor=Depends(get_current_actor),
):
    return await get_knowledge_base_manager().get_document_detail(
        user_id=_resolved_user_id(actor),
        knowledge_base_id=request.knowledge_base_id,
        document_id=request.document_id,
        page=request.page,
        page_size=request.page_size,
    )

@router.post(
    "/knowledge-bases/documents/upload",
    response_model=KnowledgeUploadSubmissionResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="上传文档",
    description="持久化文件并提交后台解析与索引任务。"
)
async def upload_documents(
    user_id: str = Form(..., description="User ID"),
    knowledge_base_id: str = Form(..., description="Knowledge base ID"),
    files: list[UploadFile] = File(..., description="Uploaded files"),
    actor=Depends(get_current_actor),
):
    """接收原始文件并提交后台入库任务。

    Args:
        user_id: 客户端传入的用户 ID，实际归属由认证主体决定。
        knowledge_base_id: 目标知识库 ID。
        files: 待上传文件。
        actor: 当前认证主体。
    """
    owner_id = _resolved_user_id(actor)
    uploaded_files: list[UploadedKnowledgeFile] = []
    for file in files:
        uploaded_files.append(
            UploadedKnowledgeFile(
                file_name=file.filename or "unnamed",
                content_type=file.content_type or "",
                data=await file.read(),
            )
        )
        await file.close()

    return await get_knowledge_base_manager().submit_uploads(
        user_id=owner_id,
        knowledge_base_id=knowledge_base_id,
        files=uploaded_files,
    )


@router.post(
    "/knowledge-bases/documents/upload-tasks",
    response_model=list[KnowledgeUploadTaskResponse],
    summary="查询上传任务状态",
)
async def list_upload_tasks(
    request: KnowledgeBaseIdentityRequest,
    actor=Depends(get_current_actor),
):
    """查询当前知识库文件后台处理阶段。

    Args:
        request: 目标知识库。
        actor: 当前访问主体。
    """
    return await get_knowledge_base_manager().list_upload_tasks(
        _resolved_user_id(actor), request.knowledge_base_id
    )

@router.post(
    "/knowledge-bases/documents/upload-tasks/retry",
    response_model=KnowledgeUploadTaskResponse,
    summary="重试失败的上传任务",
    description="把失败的上传任务重新置为排队，由后台 worker 重新解析与入库。"
)
async def retry_upload_task(
    request: KnowledgeUploadTaskRequest,
    actor=Depends(get_current_actor),
):
    """重试失败的上传任务。

    Args:
        request: 目标知识库与上传任务 ID。
        actor: 当前访问主体。
    """
    return await get_knowledge_base_manager().retry_upload_task(
        _resolved_user_id(actor), request.knowledge_base_id, request.task_id
    )

@router.post(
    "/knowledge-bases/documents/upload-tasks/delete",
    response_model=KnowledgeUploadTaskDeleteResponse,
    summary="删除失败的上传任务",
    description="删除失败的上传任务记录，原始文件继续保留在对象存储中。"
)
async def delete_upload_task(
    request: KnowledgeUploadTaskRequest,
    actor=Depends(get_current_actor),
):
    """删除失败的上传任务记录。

    Args:
        request: 目标知识库与上传任务 ID。
        actor: 当前访问主体。
    """
    return await get_knowledge_base_manager().delete_upload_task(
        _resolved_user_id(actor), request.knowledge_base_id, request.task_id
    )

@router.post(
    "/knowledge-bases/documents/update",
    response_model=KnowledgeBaseDocumentRecord,
    summary="更新文档",
    description="修改文档元数据或重新写入文档内容。"
)
async def update_document(
    request: UpdateKnowledgeBaseDocumentRequest,
    actor=Depends(get_current_actor),
):
    owner_id = _resolved_user_id(actor)
    return await get_knowledge_base_manager().update_document(
        user_id=owner_id,
        knowledge_base_id=request.knowledge_base_id,
        document_id=request.document_id,
        display_name=request.display_name,
    )

@router.post(
    "/knowledge-bases/documents/chunks/update",
    response_model=KnowledgeBaseDocumentChunkRecord,
    summary="更新切片",
    description="修改单个切片的正文内容或启用开关。"
)
async def update_document_chunk(
    request: UpdateKnowledgeChunkRequest,
    actor=Depends(get_current_actor),
):
    """更新单个切片。

    Args:
        request: 目标切片与更新字段。
        actor: 当前访问主体。
    """
    return await get_knowledge_base_manager().update_document_chunk(
        _resolved_user_id(actor),
        request.knowledge_base_id,
        request.document_id,
        request.chunk_id,
        content=request.content,
        state=request.state,
    )

@router.post("/knowledge-bases/documents/delete", summary="删除文档", description="删除指定文档及其关联索引数据。")
async def delete_document(
    request: DeleteKnowledgeBaseDocumentRequest,
    actor=Depends(get_current_actor),
):
    owner_id = _resolved_user_id(actor)
    return await get_knowledge_base_manager().delete_document(
        user_id=owner_id,
        knowledge_base_id=request.knowledge_base_id,
        document_id=request.document_id,
    )

@router.post(
    "/knowledge-bases/documents/bulk-delete",
    response_model=BulkDeleteDocumentResponse,
    summary="批量删除文档",
    description="批量删除指定知识库中的多个文档。"
)
async def bulk_delete_documents(
    request: BulkDeleteKnowledgeBaseDocumentRequest,
    actor=Depends(get_current_actor),
):
    owner_id = _resolved_user_id(actor)
    return await get_knowledge_base_manager().bulk_delete_documents(
        user_id=owner_id,
        knowledge_base_id=request.knowledge_base_id,
        document_ids=request.document_ids,
    )
