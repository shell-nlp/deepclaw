from pydantic import BaseModel, Field


class KnowledgeBaseIdentityRequest(BaseModel):
    user_id: str = Field(..., description="User ID")
    knowledge_base_id: str = Field(..., description="Knowledge base ID")


class KnowledgeBaseListRequest(BaseModel):
    user_id: str = Field(..., description="User ID")
    search: str = Field("", description="Search text")
    page: int = Field(1, description="Page number")
    page_size: int = Field(10, description="Page size")


class CreateKnowledgeBaseRequest(BaseModel):
    user_id: str = Field(..., description="User ID")
    name: str = Field(..., description="Knowledge base name")
    description: str = Field("", description="Knowledge base description")


class UpdateKnowledgeBaseRequest(BaseModel):
    user_id: str = Field(..., description="User ID")
    knowledge_base_id: str = Field(..., description="Knowledge base ID")
    name: str | None = Field(None, description="Knowledge base name")
    description: str | None = Field(None, description="Knowledge base description")


class UpdateKnowledgeBaseDocumentRequest(BaseModel):
    user_id: str = Field(..., description="User ID")
    knowledge_base_id: str = Field(..., description="Knowledge base ID")
    document_id: str = Field(..., description="Document ID")
    display_name: str = Field(..., description="Document display name")


class DeleteKnowledgeBaseDocumentRequest(BaseModel):
    user_id: str = Field(..., description="User ID")
    knowledge_base_id: str = Field(..., description="Knowledge base ID")
    document_id: str = Field(..., description="Document ID")


class DocumentListRequest(BaseModel):
    user_id: str = Field(..., description="User ID")
    knowledge_base_id: str = Field(..., description="Knowledge base ID")
    search: str = Field("", description="Search text")
    page: int = Field(1, description="Page number")
    page_size: int = Field(10, description="Page size")


class DocumentDetailRequest(BaseModel):
    user_id: str = Field(..., description="User ID")
    knowledge_base_id: str = Field(..., description="Knowledge base ID")
    document_id: str = Field(..., description="Document ID")
    page: int = Field(1, description="Page number")
    page_size: int = Field(10, description="Page size")


class BulkDeleteKnowledgeBaseRequest(BaseModel):
    user_id: str = Field(..., description="User ID")
    knowledge_base_ids: list[str] = Field(default_factory=list)


class BulkDeleteKnowledgeBaseDocumentRequest(BaseModel):
    user_id: str = Field(..., description="User ID")
    knowledge_base_id: str = Field(..., description="Knowledge base ID")
    document_ids: list[str] = Field(default_factory=list)
