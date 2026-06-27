from typing import Any, Dict, List, Tuple

from deepclaw.common.graph_rag.base import BaseGraphRAG
from deepclaw.common.vector_store.elasticsearch import ElasticsearchVectorStore


class ElasticGraphRAG(BaseGraphRAG):
    """基于 Elasticsearch 的轻量 Vector Graph RAG。"""

    def __init__(self, es: ElasticsearchVectorStore, graph_name: str, chat_model=None):
        super().__init__(vector_store=es, graph_name=graph_name, chat_model=chat_model)
        self.es = es

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
        return self.es.vector_graph_retrieve(
            query=query,
            k=k,
            index_name=self.indexes["passage"],
            entity_index_name=self.indexes["entity"],
            relation_index_name=self.indexes["relation"],
            entity_top_k=entity_top_k,
            relation_top_k=relation_top_k,
            expansion_degree=expansion_degree,
            relation_limit=relation_limit,
            query_entities=query_entities,
            return_debug=return_debug,
        )

    def _bulk_index(self, index_name: str, docs: List[Dict[str, Any]]) -> None:
        if not docs:
            return

        first_embedding = self.es.embedding_model.embed_query(docs[0]["content"])
        self._ensure_index(index_name, len(first_embedding))

        operations = []
        for index, doc in enumerate(docs):
            embedding = (
                first_embedding
                if index == 0
                else self.es.embedding_model.embed_query(doc["content"])
            )
            operations.append({"index": {"_index": index_name, "_id": doc["id"]}})
            operations.append(
                {
                    "content": doc["content"],
                    "embedding": embedding,
                    "metadata": doc.get("metadata", {}),
                }
            )

        self.es.es_client.bulk(operations=operations, refresh=True)

    def _ensure_index(self, index_name: str, dims: int) -> None:
        if self.es.es_client.indices.exists(index=index_name):
            return

        self.es.es_client.indices.create(
            index=index_name,
            mappings={
                "properties": {
                    "content": {"type": "text"},
                    "embedding": {
                        "type": "dense_vector",
                        "dims": dims,
                        "index": True,
                        "similarity": "cosine",
                    },
                    "metadata": {
                        "properties": {
                            "id": {"type": "keyword"},
                            "type": {"type": "keyword"},
                            "name": {"type": "keyword"},
                            "user_id": {"type": "keyword"},
                            "knowledge_base_id": {"type": "keyword"},
                            "knowledge_base_name": {"type": "keyword"},
                            "document_id": {"type": "keyword"},
                            "file_id": {"type": "keyword"},
                            "file_name": {"type": "keyword"},
                            "display_name": {"type": "keyword"},
                            "storage_name": {"type": "keyword"},
                            "storage_path": {"type": "keyword"},
                            "content_type": {"type": "keyword"},
                            "entity_ids": {"type": "keyword"},
                            "relation_ids": {"type": "keyword"},
                            "passage_ids": {"type": "keyword"},
                            "subject": {"type": "keyword"},
                            "predicate": {"type": "keyword"},
                            "object": {"type": "keyword"},
                        }
                    },
                }
            },
        )

    def _delete_indexes_internal(self, index_name: str) -> None:
        if self.es.es_client.indices.exists(index=index_name):
            self.es.es_client.indices.delete(index=index_name)

    def _delete_docs_internal(self, index_name: str, doc_ids: List[str]) -> int:
        if not doc_ids or not self.es.es_client.indices.exists(index=index_name):
            return 0
        operations = [
            {"delete": {"_index": index_name, "_id": doc_id}} for doc_id in doc_ids
        ]
        result = self.es.es_client.bulk(operations=operations, refresh=True)
        return sum(
            1
            for item in result.get("items", [])
            if item.get("delete", {}).get("result") == "deleted"
        )

    def _search_by_terms(
        self, index_name: str, field: str, values: List[str], size: int
    ) -> List[Dict[str, Any]]:
        if not values or not self.es.es_client.indices.exists(index=index_name):
            return []
        results = self.es.es_client.search(
            index=index_name,
            body={"query": {"terms": {field: values}}},
            size=size,
        )
        docs = []
        for hit in results["hits"]["hits"]:
            source = hit.get("_source", {})
            docs.append(
                {
                    "id": hit["_id"],
                    "content": source.get("content", ""),
                    "metadata": source.get("metadata", {}),
                }
            )
        return docs

    def _delete_or_detach_by_passage_ids(
        self,
        index_name: str,
        docs: List[Dict[str, Any]],
        deleted_passage_ids: List[str],
    ) -> Tuple[List[str], List[str]]:
        deleted_ids = []
        kept_ids = []
        deleted_passage_set = set(deleted_passage_ids)

        for doc in docs:
            metadata = dict(doc.get("metadata", {}))
            remaining_passage_ids = [
                passage_id
                for passage_id in metadata.get("passage_ids", [])
                if passage_id not in deleted_passage_set
            ]
            if remaining_passage_ids:
                metadata["passage_ids"] = remaining_passage_ids
                self.es.es_client.update(
                    index=index_name,
                    id=doc["id"],
                    doc={"metadata": metadata},
                    refresh=True,
                )
                kept_ids.append(doc["id"])
            else:
                self._delete_docs_internal(index_name, [doc["id"]])
                deleted_ids.append(doc["id"])

        return deleted_ids, kept_ids

    def _detach_relation_ids_from_entities(self, relation_ids: List[str]) -> None:
        entities = self._search_by_terms(
            self.indexes["entity"], "metadata.relation_ids", relation_ids, size=10000
        )
        relation_id_set = set(relation_ids)
        for entity in entities:
            metadata = dict(entity.get("metadata", {}))
            metadata["relation_ids"] = [
                relation_id
                for relation_id in metadata.get("relation_ids", [])
                if relation_id not in relation_id_set
            ]
            self.es.es_client.update(
                index=self.indexes["entity"],
                id=entity["id"],
                doc={"metadata": metadata},
                refresh=True,
            )
