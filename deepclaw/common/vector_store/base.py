from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class AbstractVectorStore(ABC):
    """通用向量数据库抽象基类。"""

    def resolve_index_names(
        self,
        *,
        index_name: str | None = None,
        index_names: list[str] | None = None,
    ) -> list[str] | None:
        if index_name and index_names:
            raise ValueError("index_name and index_names cannot be provided together")
        if index_name:
            return [index_name]
        if index_names is None:
            return None

        normalized = [name.strip() for name in index_names if name and name.strip()]
        unique_names = list(dict.fromkeys(normalized))
        if not unique_names:
            raise ValueError("index_names cannot be empty")
        return unique_names

    def merge_results(
        self,
        *,
        vector_results: list[dict[str, Any]],
        keyword_results: list[dict[str, Any]],
        k: int,
    ) -> list[dict[str, Any]]:
        seen_contents: set[str] = set()
        merged: list[dict[str, Any]] = []
        for item in vector_results + keyword_results:
            content = item.get("content", "")
            if content in seen_contents:
                continue
            seen_contents.add(content)
            merged.append(item)
            if len(merged) >= k:
                break
        return merged

    @abstractmethod
    def add(
        self,
        content: str,
        metadata: dict[str, Any] | None = None,
        doc_id: str | None = None,
        index_name: str | None = None,
    ) -> str: ...

    @abstractmethod
    def add_batch(
        self,
        documents: list[dict[str, Any]],
        index_name: str | None = None,
    ) -> list[str]: ...

    @abstractmethod
    def update(
        self,
        doc_id: str,
        content: str | None = None,
        metadata: dict[str, Any] | None = None,
        index_name: str | None = None,
    ) -> bool: ...

    @abstractmethod
    def delete(self, doc_id: str, index_name: str | None = None) -> bool: ...

    @abstractmethod
    def delete_batch(self, doc_ids: list[str], index_name: str | None = None) -> list[bool]: ...

    @abstractmethod
    def get(self, doc_id: str, index_name: str | None = None) -> dict[str, Any] | None: ...

    @abstractmethod
    def exists(self, doc_id: str, index_name: str | None = None) -> bool: ...

    @abstractmethod
    def count(
        self,
        filter_conditions: dict[str, Any] | None = None,
        index_name: str | None = None,
        index_names: list[str] | None = None,
    ) -> int: ...

    @abstractmethod
    def search(
        self,
        query: str | None = None,
        k: int = 3,
        filter_conditions: dict[str, Any] | None = None,
        index_name: str | None = None,
        index_names: list[str] | None = None,
    ) -> list[dict[str, Any]]: ...

    @abstractmethod
    def vector_search(
        self,
        query: str,
        k: int = 3,
        index_name: str | None = None,
        index_names: list[str] | None = None,
        min_similarity: float | None = None,
    ) -> list[dict[str, Any]]: ...

    @abstractmethod
    def keyword_search(
        self,
        query: str,
        k: int = 3,
        index_name: str | None = None,
        index_names: list[str] | None = None,
    ) -> list[dict[str, Any]]: ...

    def retrieve(
        self,
        query: str,
        k: int = 3,
        index_name: str | None = None,
        index_names: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        vector_results = self.vector_search(
            query=query,
            k=k,
            index_name=index_name,
            index_names=index_names,
        )
        keyword_results = self.keyword_search(
            query=query,
            k=k,
            index_name=index_name,
            index_names=index_names,
        )
        return self.merge_results(
            vector_results=vector_results,
            keyword_results=keyword_results,
            k=k,
        )
