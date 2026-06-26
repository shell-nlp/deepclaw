from datetime import datetime

from sqlmodel import Field, SQLModel


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


class KnowledgeBaseMetadata(SQLModel, table=True):
    __tablename__ = "knowledge_bases"

    knowledge_base_id: str = Field(primary_key=True)
    user_id: str = Field(index=True)
    name: str = Field(index=True)
    description: str = ""
    index_prefix: str = Field(index=True)
    passage_index: str = Field(index=True)
    entity_index: str = Field(index=True)
    relation_index: str = Field(index=True)
    document_count: int = 0
    chunk_count: int = 0
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)


class KnowledgeBaseDocumentMetadata(SQLModel, table=True):
    __tablename__ = "knowledge_base_documents"

    document_id: str = Field(primary_key=True)
    knowledge_base_id: str = Field(index=True)
    user_id: str = Field(index=True)
    file_name: str = Field(index=True)
    display_name: str = Field(index=True)
    content_type: str = ""
    file_size: int = 0
    chunk_count: int = 0
    storage_path: str = ""
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)
