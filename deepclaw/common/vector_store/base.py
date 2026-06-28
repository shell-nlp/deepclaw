from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class AbstractVectorStore(ABC):
    """通用向量数据库抽象基类。"""

    def resolve_index_names(
        self,
        index_names: list[str] | None = None,
    ) -> list[str] | None:
        """归一化索引名称列表：去重、去除空串。

        Args:
            index_names: 索引名称列表，为 None 时返回 None（由调用方决定全量语义）。

        Returns:
            去重后的列表，或 None。
        """
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
        """合并向量检索和关键词检索结果，按 content 去重，优先保留向量结果在前。

        Args:
            vector_results: 向量检索的结果列表（靠前，去重时优先保留）。
            keyword_results: 关键词检索的结果列表。
            k: 返回的最大条数。
        """
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
    ) -> str:
        """添加一篇文档，返回文档 ID。

        Args:
            content: 文档正文。
            metadata: 附加元数据（可选）。
            doc_id: 自定义 ID，不传则由存储层自动生成。
            index_name: 目标索引名。
        """
        ...

    @abstractmethod
    def add_batch(
        self,
        documents: list[dict[str, Any]],
        index_name: str | None = None,
    ) -> list[str]:
        """批量添加文档，返回 ID 列表。

        Args:
            documents: 每项至少含 content，可选 metadata / id。
            index_name: 目标索引名。
        """
        ...

    @abstractmethod
    def update(
        self,
        doc_id: str,
        content: str | None = None,
        metadata: dict[str, Any] | None = None,
        index_name: str | None = None,
    ) -> bool:
        """更新文档内容或元数据。至少提供一个更新字段。

        Args:
            doc_id: 文档 ID。
            content: 新正文（可选，传入时会重新生成向量）。
            metadata: 新元数据（可选）。
            index_name: 目标索引名。
        """
        ...

    @abstractmethod
    def delete(self, doc_id: str, index_name: str | None = None) -> bool:
        """删除单篇文档。

        Args:
            doc_id: 文档 ID。
            index_name: 目标索引名。
        """
        ...

    @abstractmethod
    def delete_batch(self, doc_ids: list[str], index_name: str | None = None) -> list[bool]:
        """批量删除文档，返回每项是否成功。

        Args:
            doc_ids: 文档 ID 列表。
            index_name: 目标索引名。
        """
        ...

    @abstractmethod
    def get(self, doc_id: str, index_name: str | None = None) -> dict[str, Any] | None:
        """按 ID 获取单篇文档。

        Args:
            doc_id: 文档 ID。
            index_name: 目标索引名。
        """
        ...

    @abstractmethod
    def exists(self, doc_id: str, index_name: str | None = None) -> bool:
        """检查文档是否存在。

        Args:
            doc_id: 文档 ID。
            index_name: 目标索引名。
        """
        ...

    @abstractmethod
    def count(
        self,
        filter_conditions: dict[str, Any] | None = None,
        index_names: list[str] | None = None,
    ) -> int:
        """统计符合条件的文档数量。

        Args:
            filter_conditions: 过滤条件 {字段: 值}，不同存储层的过滤语法不同。
            index_names: 目标索引列表，为 None 时表示全量索引。
        """
        ...

    @abstractmethod
    def search(
        self,
        query: str | None = None,
        k: int = 3,
        filter_conditions: dict[str, Any] | None = None,
        index_names: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """通用搜索。query 为空时仅按过滤条件返回最新文档。

        Args:
            query: 搜索关键词（可选）。
            k: 返回的最大结果数。
            filter_conditions: 过滤条件 {字段: 值}。
            index_names: 目标索引列表，为 None 时表示全量索引。
        """
        ...

    @abstractmethod
    def vector_search(
        self,
        query: str,
        k: int = 3,
        index_names: list[str] | None = None,
        min_similarity: float | None = None,
        filter_conditions: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """向量语义检索，按余弦相似度排序。

        Args:
            query: 查询文本，自动嵌入为向量。
            k: 返回的最大结果数。
            index_names: 目标索引列表，为 None 时表示全量索引。
            min_similarity: 最低相似度阈值（可选）。
            filter_conditions: 元数据过滤条件。
        """
        ...

    @abstractmethod
    def keyword_search(
        self,
        query: str,
        k: int = 3,
        index_names: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """关键词全文检索。

        Args:
            query: 搜索关键词。
            k: 返回的最大结果数。
            index_names: 目标索引列表，为 None 时表示全量索引。
        """
        ...

    @abstractmethod
    def delete_by_filter(
        self,
        filter_conditions: dict[str, Any],
        index_names: list[str] | None = None,
    ) -> int:
        """按过滤条件批量删除文档，返回删除数量。

        Args:
            filter_conditions: 过滤条件 {字段: 值}，不同后端支持语法不同。
            index_names: 目标索引列表，为 None 时表示全量索引。
        """
        ...

    @abstractmethod
    def batch_get(
        self,
        doc_ids: list[str],
        index_name: str | None = None,
    ) -> list[dict[str, Any] | None]:
        """批量获取文档，结果顺序与传入 ID 顺序一致。

        Args:
            doc_ids: 文档 ID 列表。
            index_name: 目标索引名。
        """
        ...

    def raw_search(
        self,
        body: dict[str, Any] | None = None,
        *,
        index_names: list[str] | None = None,
        **kwargs: Any,
    ) -> Any:
        """透传原生查询到后端，返回后端原始响应。

        用于调试、执行后端特有查询等场景。子类按需重写。

        Args:
            body: 查询请求体（后端原生格式）。
            index_names: 目标索引列表，为 None 时表示全量索引。
            **kwargs: 后端支持的其他参数。

        Returns:
            后端原始响应，格式取决于具体后端实现。
        """
        raise NotImplementedError(
            f"{type(self).__name__} does not support raw_search"
        )

    def retrieve(
        self,
        query: str,
        k: int = 3,
        index_names: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """混合检索：向量检索 + 关键词检索，合并去重后返回。

        Args:
            query: 查询文本。
            k: 返回的最大结果数。
            index_names: 目标索引列表，为 None 时表示全量索引。
        """
        vector_results = self.vector_search(
            query=query,
            k=k,
            index_names=index_names,
        )
        keyword_results = self.keyword_search(
            query=query,
            k=k,
            index_names=index_names,
        )
        return self.merge_results(
            vector_results=vector_results,
            keyword_results=keyword_results,
            k=k,
        )

    def refresh_embeddings(
        self,
        new_embedding_model=None,
        *,
        batch_size: int = 50,
        index_names: list[str] | None = None,
    ) -> tuple[int, int]:
        """用新嵌入模型刷新所有已有文档的向量。

        默认不支持，需要此能力的存储子类自行覆盖实现。
        """
        raise NotImplementedError(f"{type(self).__name__} 不支持 refresh_embeddings")
