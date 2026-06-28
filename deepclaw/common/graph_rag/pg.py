from typing import Any, Dict, List, Tuple

from loguru import logger

from deepclaw.common.graph_rag.base import BaseGraphRAG
from deepclaw.common.vector_store.pgsql import PgVectorStore


class PgGraphRAG(BaseGraphRAG):
    """基于 PostgreSQL pgvector 的轻量 Vector Graph RAG。"""

    def __init__(
        self,
        vector_store: PgVectorStore,
        graph_name: str,
        chat_model=None,
    ):
        super().__init__(vector_store=vector_store, graph_name=graph_name, chat_model=chat_model)
        self.pg = vector_store

    def retrieve(
        self,
        query: str,
        k: int = 6,
        entity_top_k: int = 5,
        relation_top_k: int = 8,
        expansion_degree: int = 1,
        relation_limit: int = 30,
        return_debug: bool = False,
    ) -> List[Dict[str, Any]] | Dict[str, Any]:
        query_entities = self._extract_query_entities(query)

        seed_entities = self.vector_store.vector_search(
            query=query,
            k=entity_top_k,
            index_names=[self.indexes["entity"]],
        )
        entity_ids = [d["id"] for d in seed_entities if d.get("id")]

        for entity_text in query_entities:
            extra = self.vector_store.vector_search(
                query=entity_text,
                k=entity_top_k,
                index_names=[self.indexes["entity"]],
            )
            for d in extra:
                if d.get("id") and d["id"] not in entity_ids:
                    entity_ids.append(d["id"])

        seed_relations = self.vector_store.vector_search(
            query=query,
            k=relation_top_k,
            index_names=[self.indexes["relation"]],
        )
        relation_ids = [d["id"] for d in seed_relations if d.get("id")]

        expanded_entity_ids = set(entity_ids)
        expanded_relation_ids = set(relation_ids)
        expansion_steps = []
        for degree in range(expansion_degree + 1):
            step_info: Dict[str, Any] = {"degree": degree}
            if degree > 0:
                if expanded_relation_ids:
                    new_entities = self.vector_store.vector_search(
                        query=query,
                        k=relation_top_k * 2,
                        index_names=[self.indexes["entity"]],
                        filter_conditions={
                            "metadata.relation_ids": list(expanded_relation_ids),
                        },
                    )
                    for d in new_entities:
                        expanded_entity_ids.add(d["id"])
                    step_info["new_entities_from_relations"] = len(new_entities)

                if expanded_entity_ids:
                    new_relations = self.vector_store.vector_search(
                        query=query,
                        k=entity_top_k * 2,
                        index_names=[self.indexes["relation"]],
                        filter_conditions={
                            "metadata.entity_ids": list(expanded_entity_ids),
                        },
                    )
                    for d in new_relations:
                        expanded_relation_ids.add(d["id"])
                    step_info["new_relations_from_entities"] = len(new_relations)

            expansion_steps.append(step_info)

        kept_relation_ids = list(expanded_relation_ids)
        if len(kept_relation_ids) > relation_limit:
            reranked = self.vector_store.vector_search(
                query=query,
                k=relation_limit,
                index_names=[self.indexes["relation"]],
            )
            kept_relation_ids = [d["id"] for d in reranked if d.get("id")]

        passages = self.vector_store.vector_search(
            query=query,
            k=k,
            index_names=[self.indexes["passage"]],
            filter_conditions={
                "metadata.relation_ids": kept_relation_ids,
            },
        )

        if len(passages) < k and expanded_entity_ids:
            extra_passages = self.vector_store.vector_search(
                query=query,
                k=k - len(passages),
                index_names=[self.indexes["passage"]],
                filter_conditions={
                    "metadata.entity_ids": list(expanded_entity_ids),
                },
            )
            seen_ids = {p["id"] for p in passages}
            for p in extra_passages:
                if p.get("id") not in seen_ids:
                    passages.append(p)

        if not passages:
            passages = self.vector_store.vector_search(
                query=query, k=k, index_names=[self.indexes["passage"]]
            )

        logger.info(
            "PG向量图RAG: query_entities={}, seed_entities={}, seed_relations={}, expanded_entities={}, expanded_relations={}, passages={}",
            len(query_entities),
            len(entity_ids),
            len(relation_ids),
            len(expanded_entity_ids),
            len(expanded_relation_ids),
            len(passages),
        )

        if not return_debug:
            return passages[:k]

        return {
            "query": query,
            "query_entities": query_entities,
            "passages": passages[:k],
            "seed_entity_ids": list(expanded_entity_ids),
            "seed_relation_ids": list(expanded_relation_ids),
            "expansion_steps": expansion_steps,
            "kept_relation_ids": kept_relation_ids,
        }

    def _bulk_index(self, index_name: str, docs: List[Dict[str, Any]]) -> None:
        if not docs:
            return
        self.pg.add_batch(documents=docs, index_name=index_name)

    def _delete_indexes_internal(self, index_name: str) -> None:
        rows = self.pg.search(index_names=[index_name])
        if rows:
            ids = [r["id"] for r in rows]
            self.pg.delete_batch(doc_ids=ids, index_name=index_name)

    def _delete_docs_internal(self, index_name: str, doc_ids: List[str]) -> int:
        if not doc_ids:
            return 0
        results = self.pg.delete_batch(doc_ids=doc_ids, index_name=index_name)
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
        results: List[Dict[str, Any]] = []
        for value in values:
            batch = self.pg.search(
                index_names=[index_name],
                filter_conditions={field: value},
            )
            for item in batch:
                if item not in results:
                    results.append(item)
                if len(results) >= size:
                    break
            if len(results) >= size:
                break
        return results[:size]

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
                self.pg.update(
                    doc_id=doc["id"],
                    metadata=metadata,
                    index_name=index_name,
                )
                kept_ids.append(doc["id"])
            else:
                self.pg.delete(doc_id=doc["id"], index_name=index_name)
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
            self.pg.update(
                doc_id=entity["id"],
                metadata=metadata,
                index_names=[self.indexes["entity"]],
            )
