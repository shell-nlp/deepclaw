from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from langchain_api.api.rag.schemas.knowledge_bases import (
    BulkDeleteKnowledgeBaseDocumentRequest,
    BulkDeleteKnowledgeBaseRequest,
    CreateKnowledgeBaseRequest,
    DeleteKnowledgeBaseDocumentRequest,
    DocumentDetailRequest,
    DocumentListRequest,
    KnowledgeBaseIdentityRequest,
    KnowledgeBaseListRequest,
    UpdateKnowledgeBaseDocumentRequest,
    UpdateKnowledgeBaseRequest,
)
from langchain_api.auth.dependencies import get_current_actor
from langchain_api.management.knowledge_base_manager import (
    BulkDeleteDocumentResponse,
    BulkDeleteKnowledgeBaseResponse,
    KnowledgeBaseDeleteResult,
    KnowledgeBaseDocumentDetailResponse,
    KnowledgeBaseDocumentRecord,
    KnowledgeBaseRecord,
    KnowledgeBaseUploadResponse,
    PaginatedKnowledgeBaseDocumentResponse,
    PaginatedKnowledgeBaseResponse,
    UploadedKnowledgeFile,
    knowledge_base_manager,
)


def _handle_value_error(exc: ValueError) -> HTTPException:
    return HTTPException(status_code=400, detail=str(exc))


def _owned_user_id(actor, detail: str) -> str:
    if actor.is_guest or not actor.user_id:
        raise HTTPException(status_code=403, detail=detail)
    return actor.user_id


def _resolved_user_id(actor) -> str:
    return actor.user_id if actor.user_id and not actor.is_guest else "guest"


def add_knowledge_base_management_routes(
    router: APIRouter, tags: list[str] | None = None
) -> None:
    @router.post(
        "/knowledge-bases/list",
        response_model=PaginatedKnowledgeBaseResponse,
        tags=tags,
    )
    def list_knowledge_bases(request: KnowledgeBaseListRequest, actor=Depends(get_current_actor)):
        return knowledge_base_manager.search_knowledge_bases(
            user_id=_resolved_user_id(actor),
            search=request.search,
            page=request.page,
            page_size=request.page_size,
        )

    @router.post("/knowledge-bases/create", response_model=KnowledgeBaseRecord, tags=tags)
    def create_knowledge_base(
        request: CreateKnowledgeBaseRequest,
        actor=Depends(get_current_actor),
    ):
        try:
            return knowledge_base_manager.create_knowledge_base(
                user_id=_owned_user_id(actor, "登录后可创建知识库。"),
                name=request.name,
                description=request.description,
            )
        except ValueError as exc:
            raise _handle_value_error(exc) from exc

    @router.post("/knowledge-bases/detail", response_model=KnowledgeBaseRecord, tags=tags)
    def get_knowledge_base(request: KnowledgeBaseIdentityRequest, actor=Depends(get_current_actor)):
        try:
            return knowledge_base_manager.get_knowledge_base(
                user_id=_resolved_user_id(actor),
                knowledge_base_id=request.knowledge_base_id,
            )
        except ValueError as exc:
            raise _handle_value_error(exc) from exc

    @router.post("/knowledge-bases/update", response_model=KnowledgeBaseRecord, tags=tags)
    def update_knowledge_base(
        request: UpdateKnowledgeBaseRequest,
        actor=Depends(get_current_actor),
    ):
        try:
            return knowledge_base_manager.update_knowledge_base(
                user_id=_owned_user_id(actor, "登录后可修改知识库。"),
                knowledge_base_id=request.knowledge_base_id,
                name=request.name,
                description=request.description,
            )
        except ValueError as exc:
            raise _handle_value_error(exc) from exc

    @router.post("/knowledge-bases/delete", response_model=KnowledgeBaseDeleteResult, tags=tags)
    def delete_knowledge_base(
        request: KnowledgeBaseIdentityRequest,
        actor=Depends(get_current_actor),
    ):
        try:
            return knowledge_base_manager.delete_knowledge_base(
                user_id=_owned_user_id(actor, "登录后可删除知识库。"),
                knowledge_base_id=request.knowledge_base_id,
            )
        except ValueError as exc:
            raise _handle_value_error(exc) from exc

    @router.post(
        "/knowledge-bases/bulk-delete",
        response_model=BulkDeleteKnowledgeBaseResponse,
        tags=tags,
    )
    def bulk_delete_knowledge_bases(
        request: BulkDeleteKnowledgeBaseRequest,
        actor=Depends(get_current_actor),
    ):
        try:
            return knowledge_base_manager.bulk_delete_knowledge_bases(
                user_id=_owned_user_id(actor, "登录后可批量删除知识库。"),
                knowledge_base_ids=request.knowledge_base_ids,
            )
        except ValueError as exc:
            raise _handle_value_error(exc) from exc

    @router.post(
        "/knowledge-bases/documents/list",
        response_model=PaginatedKnowledgeBaseDocumentResponse,
        tags=tags,
    )
    def list_documents(request: DocumentListRequest, actor=Depends(get_current_actor)):
        try:
            return knowledge_base_manager.search_documents(
                user_id=_resolved_user_id(actor),
                knowledge_base_id=request.knowledge_base_id,
                search=request.search,
                page=request.page,
                page_size=request.page_size,
            )
        except ValueError as exc:
            raise _handle_value_error(exc) from exc

    @router.post(
        "/knowledge-bases/documents/detail",
        response_model=KnowledgeBaseDocumentDetailResponse,
        tags=tags,
    )
    def get_document_detail(request: DocumentDetailRequest, actor=Depends(get_current_actor)):
        try:
            return knowledge_base_manager.get_document_detail(
                user_id=_resolved_user_id(actor),
                knowledge_base_id=request.knowledge_base_id,
                document_id=request.document_id,
                page=request.page,
                page_size=request.page_size,
            )
        except ValueError as exc:
            raise _handle_value_error(exc) from exc

    @router.post(
        "/knowledge-bases/documents/upload",
        response_model=KnowledgeBaseUploadResponse,
        tags=tags,
    )
    async def upload_documents(
        user_id: str = Form(..., description="User ID"),
        knowledge_base_id: str = Form(..., description="Knowledge base ID"),
        files: list[UploadFile] = File(..., description="Uploaded files"),
        actor=Depends(get_current_actor),
    ):
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

        try:
            return knowledge_base_manager.upload_documents(
                user_id=_owned_user_id(actor, "登录后可上传知识文件。"),
                knowledge_base_id=knowledge_base_id,
                files=uploaded_files,
            )
        except ValueError as exc:
            raise _handle_value_error(exc) from exc

    @router.post(
        "/knowledge-bases/documents/update",
        response_model=KnowledgeBaseDocumentRecord,
        tags=tags,
    )
    def update_document(
        request: UpdateKnowledgeBaseDocumentRequest,
        actor=Depends(get_current_actor),
    ):
        try:
            return knowledge_base_manager.update_document(
                user_id=_owned_user_id(actor, "登录后可重命名知识文件。"),
                knowledge_base_id=request.knowledge_base_id,
                document_id=request.document_id,
                display_name=request.display_name,
            )
        except ValueError as exc:
            raise _handle_value_error(exc) from exc

    @router.post("/knowledge-bases/documents/delete", tags=tags)
    def delete_document(
        request: DeleteKnowledgeBaseDocumentRequest,
        actor=Depends(get_current_actor),
    ):
        try:
            return knowledge_base_manager.delete_document(
                user_id=_owned_user_id(actor, "登录后可删除知识文件。"),
                knowledge_base_id=request.knowledge_base_id,
                document_id=request.document_id,
            )
        except ValueError as exc:
            raise _handle_value_error(exc) from exc

    @router.post(
        "/knowledge-bases/documents/bulk-delete",
        response_model=BulkDeleteDocumentResponse,
        tags=tags,
    )
    def bulk_delete_documents(
        request: BulkDeleteKnowledgeBaseDocumentRequest,
        actor=Depends(get_current_actor),
    ):
        try:
            return knowledge_base_manager.bulk_delete_documents(
                user_id=_owned_user_id(actor, "登录后可批量删除知识文件。"),
                knowledge_base_id=request.knowledge_base_id,
                document_ids=request.document_ids,
            )
        except ValueError as exc:
            raise _handle_value_error(exc) from exc
