from typing import Any, Dict, List, Tuple

from deepclaw.common.graph_rag.base import BaseGraphRAG
from deepclaw.common.vector_store.base import AbstractVectorStore


class PgGraphRAG(BaseGraphRAG):
    """基于 PostgreSQL pgvector 的轻量 Vector Graph RAG。"""

    def __init__(
        self,
        vector_store: AbstractVectorStore,
        graph_name: str,
        chat_model=None,
    ):
        super().__init__(vector_store=vector_store, graph_name=graph_name, chat_model=chat_model)

    def _bulk_index(self, index_name: str, docs: List[Dict[str, Any]]) -> None:
        if not docs:
            return
        self.vector_store.add_batch(documents=docs, index_name=index_name)

    def _delete_indexes_internal(self, index_name: str) -> None:
        self.vector_store.clear_index(index_name)

    def _delete_docs_internal(self, index_name: str, doc_ids: List[str]) -> int:
        if not doc_ids:
            return 0
        results = self.vector_store.delete_batch(doc_ids=doc_ids, index_name=index_name)
        return sum(1 for r in results if r)

    def _search_by_terms(
        self,
        index_name: str,
        field: str,
        values: List[str],
        size: int,
    ) -> List[Dict[str, Any]]:
        if not values:
            return []
        return self.vector_store.search(
            index_names=[index_name],
            filter_conditions={field: values},
            k=size,
        )

    def _delete_or_detach_by_passage_ids(
        self,
        index_name: str,
        docs: List[Dict[str, Any]],
        deleted_passage_ids: List[str],
    ) -> Tuple[List[str], List[str]]:
        deleted_ids: List[str] = []
        kept_ids: List[str] = []
        deleted_set = set(deleted_passage_ids)

        for doc in docs:
            metadata = dict(doc.get("metadata", {}))
            remaining = [
                pid for pid in metadata.get("passage_ids", [])
                if pid not in deleted_set
            ]
            if remaining:
                metadata["passage_ids"] = remaining
                self.vector_store.update(
                    doc_id=doc["id"],
                    metadata=metadata,
                    index_name=index_name,
                )
                kept_ids.append(doc["id"])
            else:
                self.vector_store.delete(doc_id=doc["id"], index_name=index_name)
                deleted_ids.append(doc["id"])

        return deleted_ids, kept_ids

    def _detach_relation_ids_from_entities(self, relation_ids: List[str]) -> None:
        if not relation_ids:
            return
        relation_set = set(relation_ids)
        entities = self._search_by_terms(
            self.indexes["entity"],
            "metadata.relation_ids",
            relation_ids,
            size=10000,
        )
        for entity in entities:
            metadata = dict(entity.get("metadata", {}))
            metadata["relation_ids"] = [
                rid for rid in metadata.get("relation_ids", [])
                if rid not in relation_set
            ]
            self.vector_store.update(
                doc_id=entity["id"],
                metadata=metadata,
                index_name=self.indexes["entity"],
            )
