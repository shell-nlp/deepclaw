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

    @staticmethod
    def merge_results_rrf(
        *,
        vector_results: list[dict[str, Any]],
        keyword_results: list[dict[str, Any]],
        k: int,
        rrf_k: int = 60,
    ) -> list[dict[str, Any]]:
        """用 RRF（倒数排名融合）合并向量检索与关键词检索结果。

        Args:
            vector_results: 向量检索结果，按相关性从高到低排列。
            keyword_results: 关键词（BM25）检索结果，按相关性从高到低排列。
            k: 返回的最大条数。
            rrf_k: RRF 平滑参数，数值越大越弱化头部排名差异。

        Returns:
            按融合分数从高到低排列、并按文档 ID 去重后的结果。
        """
        scores: dict[str, float] = {}
        items: dict[str, dict[str, Any]] = {}
        best_rank: dict[str, int] = {}
        first_list: dict[str, int] = {}
        for list_index, rank_list in enumerate((vector_results, keyword_results)):
            for rank, item in enumerate(rank_list, start=1):
                key = str(item.get("id") or item.get("content", ""))
                if not key:
                    continue
                scores[key] = scores.get(key, 0.0) + 1.0 / (rrf_k + rank)
                items.setdefault(key, item)
                best_rank[key] = min(best_rank.get(key, rank), rank)
                first_list.setdefault(key, list_index)
        # 两路候选常常互不重合，此时同分项必须按排名交替取，否则排在前面的那一路会独占结果。
        ordered = sorted(
            scores,
            key=lambda key: (-scores[key], best_rank[key], first_list[key]),
        )
        # 再给每个通道保底名额：单路独有的高分命中不应被另一路的“共识噪声”整体挤出。
        quota = max(1, k // 3)
        head = ordered[: max(0, k - 2 * quota)]
        selected = list(head)
        selected_keys = set(head)
        for rank_list in (vector_results, keyword_results):
            kept = 0
            for item in rank_list[:quota]:
                key = str(item.get("id") or item.get("content", ""))
                if key not in scores or key in selected_keys:
                    continue
                selected.append(key)
                selected_keys.add(key)
                kept += 1
                if kept >= quota:
                    break
        for key in ordered:
            if len(selected) >= k:
                break
            if key not in selected_keys:
                selected.append(key)
                selected_keys.add(key)
        return [
            {**items[key], "score": scores[key], "raw_score": items[key].get("score")}
            for key in selected
        ]

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

    def vector_search_by_ids(
        self, query: str, doc_ids: list[str], index_name: str, k: int
    ) -> list[dict[str, Any]]:
        """限定候选 ID 进行向量检索。

        Args:
            query: 查询文本。
            doc_ids: 候选文档 ID。
            index_name: 索引名称。
            k: 返回数量上限。
        """
        raise NotImplementedError(
            f"{type(self).__name__} does not support vector_search_by_ids"
        )

    def list_ids_by_filter(
        self, index_name: str, filter_conditions: dict[str, Any]
    ) -> list[str]:
        """获取指定索引内符合过滤条件的全部文档 ID。

        Args:
            index_name: 目标索引名称。
            filter_conditions: 精确匹配的过滤条件。
        """
        raise NotImplementedError(
            f"{type(self).__name__} does not support list_ids_by_filter"
        )

    def clear_index(self, index_name: str) -> None:
        """清除指定索引的所有记录。

        Args:
            index_name: 待清空的索引名称。
        """
        while rows := self.search(k=500, index_names=[index_name]):
            self.delete_batch(
                doc_ids=[str(row["id"]) for row in rows], index_name=index_name
            )

    @abstractmethod
    def keyword_search(
        self,
        query: str,
        k: int = 3,
        index_names: list[str] | None = None,
        filter_conditions: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """关键词全文检索。

        Args:
            query: 搜索关键词。
            k: 返回的最大结果数。
            index_names: 目标索引列表，为 None 时表示全量索引。
            filter_conditions: 元数据过滤条件。
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

    def retrieve_with_rrf(
        self,
        query: str,
        k: int = 3,
        index_names: list[str] | None = None,
        rrf_k: int = 60,
        filter_conditions: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """混合检索：BM25 关键词检索与向量检索按 RRF 融合后返回。

        Args:
            query: 查询文本。
            k: 返回的最大结果数。
            index_names: 目标索引列表，为 None 时表示全量索引。
            rrf_k: RRF 平滑参数。
            filter_conditions: 元数据过滤条件；值为 ``{"$ne": x}`` 时表示不等值，缺失该字段的文档也视为满足。
        """
        candidate_k = max(k * 4, 20)
        vector_results = self.vector_search(
            query=query,
            k=candidate_k,
            index_names=index_names,
            filter_conditions=filter_conditions,
        )
        keyword_results = self.keyword_search(
            query=query,
            k=candidate_k,
            index_names=index_names,
            filter_conditions=filter_conditions,
        )
        return self.merge_results_rrf(
            vector_results=vector_results,
            keyword_results=keyword_results,
            k=k,
            rrf_k=rrf_k,
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
