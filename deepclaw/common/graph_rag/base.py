import hashlib
import uuid
from abc import ABC, abstractmethod
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

from langchain_core.documents import Document
from loguru import logger
from pydantic import BaseModel, Field

from deepclaw.common.vector_store.base import AbstractVectorStore
from deepclaw.utils import get_chat_model

TRIPLET_PROMPT = """从文本中抽取知识图谱三元组。

要求：
- 只抽取文本明确表达的事实，不要补充常识。
- subject/object 使用简洁实体名。
- predicate 使用简短中文或英文关系短语。
- 最多返回 20 个三元组。
- 只返回 JSON，格式：{{"triplets":[{{"subject":"...","predicate":"...","object":"..."}}]}}

文本：
{text}
"""

QUERY_ENTITY_PROMPT = """从问题中抽取检索知识图谱需要的实体名。
只返回 JSON：{{"entities":["..."]}}

问题：
{query}
"""


class ExtractedTriplet(BaseModel):
    subject: str = Field(description="主语实体")
    predicate: str = Field(description="关系谓词")
    object: str = Field(description="宾语实体")


class TripletExtractionResult(BaseModel):
    triplets: List[ExtractedTriplet] = Field(
        default_factory=list, description="从文本中明确抽取出的三元组"
    )


class QueryEntityExtractionResult(BaseModel):
    entities: List[str] = Field(default_factory=list, description="问题中的实体名")


class BaseGraphRAG(ABC):
    """GraphRAG 抽象基类，共享图构建与 CRUD 编排逻辑。"""

    def __init__(self, vector_store: AbstractVectorStore, graph_name: str, chat_model=None):
        self.vector_store = vector_store
        self.graph_name = graph_name
        self.chat_model = chat_model
        self.indexes = self.index_names(graph_name)

    @staticmethod
    def index_names(prefix: str) -> Dict[str, str]:
        return {
            "passage": f"{prefix}_passages",
            "entity": f"{prefix}_entities",
            "relation": f"{prefix}_relations",
        }

    def add_texts(
        self,
        texts: List[str],
        metadatas: Optional[List[Dict[str, Any]]] = None,
        ids: Optional[List[str]] = None,
        extract_triplets: bool = True,
    ) -> Dict[str, Any]:
        documents = []
        for index, text in enumerate(texts):
            metadata = metadatas[index] if metadatas and index < len(metadatas) else {}
            doc_id = ids[index] if ids and index < len(ids) else str(uuid.uuid4())
            documents.append(Document(page_content=text, metadata=metadata, id=doc_id))
        return self.add_documents(documents, extract_triplets=extract_triplets)

    def add_documents(
        self, documents: List[Document], extract_triplets: bool = True
    ) -> Dict[str, Any]:
        """增量写入篇章，并保留已有实体与关系的邻接信息。

        Args:
            documents: 待写入的篇章列表。
            extract_triplets: 是否从正文提取三元组。
        """
        if not documents:
            return {
                "graph_name": self.graph_name,
                "indexes": self.indexes,
                "passage_count": 0,
                "entity_count": 0,
                "relation_count": 0,
            }
        graph = self.build_graph(documents, extract_triplets=extract_triplets)
        return self._write_graph(graph)

    def _write_graph(self, graph: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
        """合并并写入已构建的图谱记录。

        Args:
            graph: 包含篇章、实体和关系记录的图谱。
        """
        # 先收集旧 passage 关联；重新写入时只移除本批不再引用的边。
        passage_ids = [str(doc["id"]) for doc in graph["passages"]]
        existing_passages = self.vector_store.batch_get(
            passage_ids, index_name=self.indexes["passage"]
        )
        new_passage_relations = {
            str(doc["id"]): set(doc["metadata"]["relation_ids"])
            for doc in graph["passages"]
        }
        new_passage_entities = {
            str(doc["id"]): set(doc["metadata"]["entity_ids"])
            for doc in graph["passages"]
        }
        old_passage_relations = {
            str(passage["id"]): set((passage.get("metadata") or {}).get("relation_ids", []))
            for passage in existing_passages
            if passage
        }
        old_passage_entities = {
            str(passage["id"]): set((passage.get("metadata") or {}).get("entity_ids", []))
            for passage in existing_passages
            if passage
        }
        old_relation_ids = set().union(*old_passage_relations.values())
        old_entity_ids = set().union(*old_passage_entities.values())
        deleted_relation_ids: set[str] = set()
        for kind, old_links, new_links, linked_ids in (
            ("relation", old_passage_relations, new_passage_relations, old_relation_ids),
            ("entity", old_passage_entities, new_passage_entities, old_entity_ids),
        ):
            removed_by_id = {
                item_id: {
                    passage_id
                    for passage_id, ids in old_links.items()
                    if item_id in ids and item_id not in new_links[passage_id]
                }
                for item_id in linked_ids
            }
            removed_ids = {item_id for item_id, ids in removed_by_id.items() if ids}
            if not removed_ids:
                continue
            existing = self.vector_store.batch_get(
                sorted(removed_ids), index_name=self.indexes[kind]
            )
            for previous in existing:
                if not previous:
                    continue
                metadata = dict(previous.get("metadata") or {})
                remaining = sorted(
                    set(metadata.get("passage_ids") or [])
                    - removed_by_id[str(previous["id"])]
                )
                if remaining:
                    metadata["passage_ids"] = remaining
                    self.vector_store.update(
                        doc_id=str(previous["id"]),
                        metadata=metadata,
                        index_name=self.indexes[kind],
                    )
                else:
                    self.vector_store.delete(
                        doc_id=str(previous["id"]), index_name=self.indexes[kind]
                    )
                    if kind == "relation":
                        deleted_relation_ids.add(str(previous["id"]))
        if deleted_relation_ids:
            self._detach_relation_ids_from_entities(sorted(deleted_relation_ids))

        for kind, old_links, new_links in (
            ("entity", old_passage_entities, new_passage_entities),
            ("relation", old_passage_relations, new_passage_relations),
        ):
            index_name = self.indexes[kind]
            docs = graph["entities" if kind == "entity" else "relations"]
            existing = self.vector_store.batch_get(
                [str(doc["id"]) for doc in docs], index_name=index_name
            )
            for doc, previous in zip(docs, existing):
                if previous:
                    metadata = dict(doc["metadata"])
                    old_metadata = previous.get("metadata") or {}
                    for field in ("passage_ids", "relation_ids", "entity_ids"):
                        if field in metadata:
                            previous_values = set(old_metadata.get(field) or [])
                            if field == "passage_ids":
                                previous_values -= {
                                    passage_id for passage_id, ids in old_links.items()
                                    if str(doc["id"]) in ids
                                    and str(doc["id"]) not in new_links[passage_id]
                                }
                            if field == "relation_ids" and kind == "entity":
                                previous_values -= deleted_relation_ids
                            metadata[field] = sorted(set(metadata[field]) | previous_values)
                    doc["metadata"] = metadata

        self._bulk_index(self.indexes["entity"], graph["entities"])
        self._bulk_index(self.indexes["relation"], graph["relations"])
        self._bulk_index(self.indexes["passage"], graph["passages"])

        result = {
            "graph_name": self.graph_name,
            "indexes": self.indexes,
            "passage_count": len(graph["passages"]),
            "entity_count": len(graph["entities"]),
            "relation_count": len(graph["relations"]),
        }
        logger.info("向量图索引完成: {}", result)
        return result

    def upsert_documents_by_source(
        self,
        documents: List[Document],
        *,
        source: str,
        source_field: str = "document_id",
        extract_triplets: bool = True,
    ) -> Dict[str, Any]:
        """以来源为单位替换全部篇章和图谱关联。

        Args:
            documents: 此来源的完整篇章集合，空列表表示删除来源。
            source: 稳定的来源标识。
            source_field: 篇章元数据中保存来源的字段。
            extract_triplets: 是否提取三元组。
        """
        source = source.strip()
        if not source or not source_field.isidentifier():
            raise ValueError("source 或 source_field 不合法")
        for document in documents:
            metadata = dict(document.metadata or {})
            if source_field in metadata and str(metadata[source_field]) != source:
                raise ValueError("篇章元数据中的来源与 source 不一致")
            metadata[source_field] = source
            document.metadata = metadata
        # 先构建新图，抽取失败时旧数据仍可用；删除阶段只针对这一来源。
        graph = self.build_graph(documents, extract_triplets=extract_triplets)
        old_ids = self.vector_store.list_ids_by_filter(
            self.indexes["passage"], {f"metadata.{source_field}": source}
        )
        for offset in range(0, len(old_ids), 500):
            self.delete_documents(old_ids[offset:offset + 500])
        # add_documents 保持原有返回格式与邻接合并行为。
        if not documents:
            return {
                "graph_name": self.graph_name,
                "indexes": self.indexes,
                "passage_count": 0,
                "entity_count": 0,
                "relation_count": 0,
            }
        return self._write_graph(graph)

    def delete_documents_by_source(
        self, source: str, *, source_field: str = "document_id"
    ) -> Dict[str, Any]:
        """删除一个来源的所有篇章及失效图谱关联。

        Args:
            source: 稳定的来源标识。
            source_field: 篇章元数据中的来源字段。
        """
        source = source.strip()
        if not source or not source_field.isidentifier():
            raise ValueError("source 或 source_field 不合法")
        ids = self.vector_store.list_ids_by_filter(
            self.indexes["passage"], {f"metadata.{source_field}": source}
        )
        result = {
            "deleted_passages": 0,
            "deleted_relations": 0,
            "deleted_entities": 0,
            "detached_relations": 0,
        }
        for offset in range(0, len(ids), 500):
            batch = self.delete_documents(ids[offset:offset + 500])
            for key, count in batch.items():
                result[key] += count
        return result

    def delete_graph(self, ignore_missing: bool = True) -> Dict[str, Any]:
        deleted = {}
        for kind, index_name in self.indexes.items():
            try:
                self._delete_indexes_internal(index_name)
                deleted[kind] = "deleted"
            except Exception:
                if not ignore_missing:
                    raise
                deleted[kind] = "missing"

        return {
            "graph_name": self.graph_name,
            "indexes": self.indexes,
            "result": deleted,
        }

    def delete_documents(self, doc_ids: List[str]) -> Dict[str, Any]:
        """删除篇章及不再被引用的实体和关系。

        Args:
            doc_ids: 待删除的篇章 ID。
        """
        doc_ids = [str(doc_id) for doc_id in doc_ids if doc_id]
        if not doc_ids:
            return {
                "deleted_passages": 0,
                "deleted_relations": 0,
                "deleted_entities": 0,
            }

        passages = self.vector_store.batch_get(
            doc_ids, index_name=self.indexes["passage"]
        )
        relation_ids = sorted({
            str(relation_id)
            for passage in passages if passage
            for relation_id in (passage.get("metadata") or {}).get("relation_ids", [])
        })
        entity_ids = sorted({
            str(entity_id)
            for passage in passages if passage
            for entity_id in (passage.get("metadata") or {}).get("entity_ids", [])
        })
        relations = [
            doc for doc in self.vector_store.batch_get(
                relation_ids, index_name=self.indexes["relation"]
            ) if doc
        ]
        entities = [
            doc for doc in self.vector_store.batch_get(
                entity_ids, index_name=self.indexes["entity"]
            ) if doc
        ]

        deleted_passages = self._delete_docs_internal(self.indexes["passage"], doc_ids)
        deleted_relations, kept_relation_ids = self._delete_or_detach_by_passage_ids(
            index_name=self.indexes["relation"],
            docs=relations,
            deleted_passage_ids=doc_ids,
        )
        deleted_entities, _ = self._delete_or_detach_by_passage_ids(
            index_name=self.indexes["entity"],
            docs=entities,
            deleted_passage_ids=doc_ids,
        )

        if deleted_relations:
            self._detach_relation_ids_from_entities(deleted_relations)

        return {
            "deleted_passages": deleted_passages,
            "deleted_relations": len(deleted_relations),
            "deleted_entities": len(deleted_entities),
            "detached_relations": len(kept_relation_ids),
        }

    def delete_by_query(self, query: str) -> Dict[str, Any]:
        result = self.retrieve(query=query, k=100, return_debug=False)
        doc_ids = [
            str(doc.get("metadata", {}).get("id") or doc.get("id")) for doc in result
        ]
        return self.delete_documents(doc_ids)

    def build_graph(
        self, documents: List[Document], extract_triplets: bool = True
    ) -> Dict[str, List[Dict[str, Any]]]:
        entity_name_to_id: Dict[str, str] = {}
        relation_text_to_id: Dict[str, str] = {}
        entity_to_relation_ids: Dict[str, set] = defaultdict(set)
        entity_to_passage_ids: Dict[str, set] = defaultdict(set)
        relation_to_entity_ids: Dict[str, set] = defaultdict(set)
        relation_to_passage_ids: Dict[str, set] = defaultdict(set)
        passage_to_entity_ids: Dict[str, set] = defaultdict(set)
        passage_to_relation_ids: Dict[str, set] = defaultdict(set)
        relation_triplets: Dict[str, Tuple[str, str, str]] = {}

        for document in documents:
            passage_id = str(document.id or uuid.uuid4())
            document.id = passage_id
            triplets = self._get_document_triplets(document, extract_triplets)

            for subject, predicate, object_ in triplets:
                subject_id = self._get_entity_id(subject, entity_name_to_id)
                object_id = self._get_entity_id(object_, entity_name_to_id)
                relation_text = f"{subject} {predicate} {object_}"
                relation_id = relation_text_to_id.setdefault(
                    self._normalize(relation_text),
                    self._stable_id("rel", relation_text),
                )

                relation_triplets[relation_id] = (subject, predicate, object_)
                relation_to_entity_ids[relation_id].update([subject_id, object_id])
                relation_to_passage_ids[relation_id].add(passage_id)
                entity_to_relation_ids[subject_id].add(relation_id)
                entity_to_relation_ids[object_id].add(relation_id)
                entity_to_passage_ids[subject_id].add(passage_id)
                entity_to_passage_ids[object_id].add(passage_id)
                passage_to_entity_ids[passage_id].update([subject_id, object_id])
                passage_to_relation_ids[passage_id].add(relation_id)

        return {
            "entities": self._build_entity_docs(
                entity_name_to_id, entity_to_relation_ids, entity_to_passage_ids
            ),
            "relations": self._build_relation_docs(
                relation_triplets, relation_to_entity_ids, relation_to_passage_ids
            ),
            "passages": self._build_passage_docs(
                documents, passage_to_entity_ids, passage_to_relation_ids
            ),
        }

    def _build_entity_docs(
        self,
        entity_name_to_id: Dict[str, str],
        entity_to_relation_ids: Dict[str, set],
        entity_to_passage_ids: Dict[str, set],
    ) -> List[Dict[str, Any]]:
        id_to_entity_name = {
            entity_id: name for name, entity_id in entity_name_to_id.items()
        }
        return [
            {
                "id": entity_id,
                "content": entity_name,
                "metadata": {
                    "id": entity_id,
                    "name": entity_name,
                    "type": "entity",
                    "relation_ids": sorted(entity_to_relation_ids[entity_id]),
                    "passage_ids": sorted(entity_to_passage_ids[entity_id]),
                },
            }
            for entity_id, entity_name in id_to_entity_name.items()
        ]

    def _build_relation_docs(
        self,
        relation_triplets: Dict[str, Tuple[str, str, str]],
        relation_to_entity_ids: Dict[str, set],
        relation_to_passage_ids: Dict[str, set],
    ) -> List[Dict[str, Any]]:
        docs = []
        for relation_id, (subject, predicate, object_) in relation_triplets.items():
            docs.append(
                {
                    "id": relation_id,
                    "content": f"{subject} {predicate} {object_}",
                    "metadata": {
                        "id": relation_id,
                        "type": "relation",
                        "entity_ids": sorted(relation_to_entity_ids[relation_id]),
                        "passage_ids": sorted(relation_to_passage_ids[relation_id]),
                        "subject": subject,
                        "predicate": predicate,
                        "object": object_,
                    },
                }
            )
        return docs

    def _build_passage_docs(
        self,
        documents: List[Document],
        passage_to_entity_ids: Dict[str, set],
        passage_to_relation_ids: Dict[str, set],
    ) -> List[Dict[str, Any]]:
        docs = []
        for document in documents:
            passage_id = str(document.id)
            metadata = dict(document.metadata or {})
            metadata.update(
                {
                    "id": passage_id,
                    "type": "passage",
                    "entity_ids": sorted(passage_to_entity_ids[passage_id]),
                    "relation_ids": sorted(passage_to_relation_ids[passage_id]),
                }
            )
            docs.append(
                {
                    "id": passage_id,
                    "content": document.page_content,
                    "metadata": metadata,
                }
            )
        return docs

    def _get_document_triplets(
        self, document: Document, extract_triplets: bool
    ) -> List[Tuple[str, str, str]]:
        raw_triplets = document.metadata.get("triplets") if document.metadata else None
        if raw_triplets:
            return self._parse_triplets(raw_triplets)
        if not extract_triplets:
            return []
        return self._extract_triplets(document.page_content)

    def _extract_triplets(self, text: str) -> List[Tuple[str, str, str]]:
        model = self._get_chat_model().with_structured_output(
            TripletExtractionResult, method="json_mode"
        )
        result: TripletExtractionResult = model.invoke(TRIPLET_PROMPT.format(text=text))
        return [
            (triplet.subject, triplet.predicate, triplet.object)
            for triplet in result.triplets
            if triplet.subject and triplet.predicate and triplet.object
        ]

    def _extract_query_entities(self, query: str) -> List[str]:
        try:
            model = self._get_chat_model().with_structured_output(
                QueryEntityExtractionResult, method="json_mode"
            )
            result: QueryEntityExtractionResult = model.invoke(
                QUERY_ENTITY_PROMPT.format(query=query)
            )
            return [
                str(entity).strip() for entity in result.entities if str(entity).strip()
            ]
        except Exception as exc:
            logger.warning("查询实体抽取失败，使用简单切词: {}", exc)
            return self._simple_extract_entities(query)

    def _get_chat_model(self):
        if self.chat_model is None:
            self.chat_model = get_chat_model()
        return self.chat_model

    @classmethod
    def _parse_triplets(cls, raw_triplets: Any) -> List[Tuple[str, str, str]]:
        triplets = []
        for item in raw_triplets or []:
            if isinstance(item, dict):
                subject = item.get("subject") or item.get("head")
                predicate = item.get("predicate") or item.get("relation")
                object_ = item.get("object") or item.get("tail")
            elif isinstance(item, (list, tuple)) and len(item) >= 3:
                subject, predicate, object_ = item[:3]
            else:
                continue

            subject = str(subject or "").strip()
            predicate = str(predicate or "").strip()
            object_ = str(object_ or "").strip()
            if subject and predicate and object_:
                triplets.append((subject, predicate, object_))

        return list(dict.fromkeys(triplets))

    @classmethod
    def _get_entity_id(cls, entity_name: str, entity_name_to_id: Dict[str, str]) -> str:
        normalized = cls._normalize(entity_name)
        if normalized not in entity_name_to_id:
            entity_name_to_id[normalized] = cls._stable_id("ent", normalized)
        return entity_name_to_id[normalized]

    @classmethod
    def _stable_id(cls, prefix: str, text: str) -> str:
        digest = hashlib.md5(cls._normalize(text).encode("utf-8")).hexdigest()
        return f"{prefix}_{digest}"

    @staticmethod
    def _normalize(text: str) -> str:
        return " ".join(str(text).lower().strip().split())

    @staticmethod
    def _simple_extract_entities(query: str) -> List[str]:
        words = []
        for raw_word in query.replace("，", " ").replace("。", " ").split():
            word = raw_word.strip("'\".,;:!?()[]{}<>《》、")
            if len(word) >= 2:
                words.append(word)
        return list(dict.fromkeys(words))[:8]

    def retrieve(
        self,
        query: str,
        k: int = 6,
        entity_top_k: int = 5,
        relation_top_k: int = 8,
        expansion_degree: int = 1,
        relation_limit: int = 30,
        return_debug: bool = False,
        min_similarity: float | None = None,
        filter_conditions: Dict[str, Any] | None = None,
    ) -> List[Dict[str, Any]] | Dict[str, Any]:
        """跨存储后端检索实体、关系与关联篇章。

        Args:
            query: 检索问题。
            k: 最多返回篇章数量。
            entity_top_k: 每个实体查询的召回数量。
            relation_top_k: 关系召回数量。
            expansion_degree: 邻接扩展轮数。
            relation_limit: 图中最多保留的候选关系数。
            return_debug: 是否返回中间检索信息。
            min_similarity: 实体、关系和篇章的最低向量分数。
            filter_conditions: 篇章元数据精确过滤条件。
        """
        if k <= 0:
            return [] if not return_debug else {"query": query, "passages": []}
        if min(entity_top_k, relation_top_k, relation_limit) < 0 or expansion_degree < 0:
            raise ValueError("召回数量和扩展轮数不能为负数")
        store = self.vector_store
        entity_index = self.indexes["entity"]
        relation_index = self.indexes["relation"]
        passage_index = self.indexes["passage"]
        query_entities = self._extract_query_entities(query)
        seed_entities = []
        for text in query_entities or [query]:
            if entity_top_k == 0:
                break
            seed_entities.extend(store.vector_search(
                query=text, k=entity_top_k, index_names=[entity_index],
                min_similarity=min_similarity,
            ))
        seed_relations = store.vector_search(
            query=query, k=relation_top_k, index_names=[relation_index],
            min_similarity=min_similarity,
        ) if relation_top_k else []
        entity_ids = set(str(item["id"]) for item in seed_entities if item.get("id"))
        relation_ids = set(str(item["id"]) for item in seed_relations if item.get("id"))
        allowed_passages = (
            set(store.list_ids_by_filter(passage_index, filter_conditions))
            if filter_conditions else None
        )
        expanded_entities = set(entity_ids)
        expanded_relations = set(relation_ids)
        steps: list[dict[str, Any]] = []
        frontier_entities = set(entity_ids)
        frontier_relations = set(relation_ids)
        for degree in range(expansion_degree + 1):
            new_relations = set()
            for entity in store.batch_get(sorted(frontier_entities), index_name=entity_index):
                if entity:
                    new_relations.update(
                        (entity.get("metadata") or {}).get("relation_ids") or []
                    )
            new_relations -= expanded_relations
            expanded_relations.update(new_relations)
            if degree == expansion_degree:
                steps.append({
                    "degree": degree,
                    "entity_count": len(expanded_entities),
                    "relation_count": len(expanded_relations),
                })
                break
            new_entities = set()
            for relation in store.batch_get(
                sorted(frontier_relations | new_relations), index_name=relation_index
            ):
                if relation:
                    new_entities.update(
                        (relation.get("metadata") or {}).get("entity_ids") or []
                    )
            new_entities -= expanded_entities
            expanded_entities.update(new_entities)
            frontier_entities = new_entities
            frontier_relations = new_relations
            steps.append({
                "degree": degree,
                "entity_count": len(expanded_entities),
                "relation_count": len(expanded_relations),
            })
        if allowed_passages is not None:
            expanded_relations = {
                str(relation["id"])
                for relation in store.batch_get(
                    sorted(expanded_relations), index_name=relation_index
                )
                if relation and allowed_passages.intersection(
                    (relation.get("metadata") or {}).get("passage_ids") or []
                )
            }
        kept_relations = sorted(expanded_relations)
        if relation_limit == 0:
            kept_relations = []
        eviction = {
            "occurred": len(kept_relations) > relation_limit,
            "before_count": len(kept_relations),
        }
        if len(kept_relations) > relation_limit:
            kept_relations = [
                str(item["id"])
                for item in store.vector_search_by_ids(
                    query=query, doc_ids=kept_relations,
                    index_name=relation_index, k=relation_limit,
                )
            ]
        eviction["after_count"] = len(kept_relations)

        candidate_ids: set[str] = set()
        for relation in store.batch_get(kept_relations, index_name=relation_index):
            if relation:
                candidate_ids.update(
                    (relation.get("metadata") or {}).get("passage_ids") or []
                )
        if not candidate_ids:
            for entity in store.batch_get(sorted(expanded_entities), index_name=entity_index):
                if entity:
                    candidate_ids.update(
                        (entity.get("metadata") or {}).get("passage_ids") or []
                    )
        if allowed_passages is not None:
            candidate_ids &= allowed_passages
        passages = store.vector_search_by_ids(
            query=query, doc_ids=sorted(candidate_ids), index_name=passage_index, k=k
        ) if candidate_ids else []
        if min_similarity is not None:
            passages = [
                item for item in passages
                if item.get("score") is None or item["score"] >= min_similarity
            ]
        if len(passages) < k:
            fallback = store.vector_search(
                query=query, k=k, index_names=[passage_index],
                min_similarity=min_similarity, filter_conditions=filter_conditions,
            )
            seen = {item["id"] for item in passages}
            for item in fallback:
                if allowed_passages is not None and item["id"] not in allowed_passages:
                    continue
                if (
                    min_similarity is not None
                    and item.get("score") is not None
                    and item["score"] < min_similarity
                ):
                    continue
                if item["id"] not in seen:
                    passages.append(item)
                    seen.add(item["id"])
                if len(passages) >= k:
                    break
        if not return_debug:
            return passages[:k]
        return {
            "query": query,
            "query_entities": query_entities,
            "passages": passages[:k],
            "seed_entity_ids": sorted(entity_ids),
            "seed_relation_ids": sorted(relation_ids),
            "expanded_entity_ids": sorted(expanded_entities),
            "expanded_relation_ids": sorted(expanded_relations),
            "kept_relation_ids": kept_relations,
            "expansion_steps": steps,
            "eviction": eviction,
        }

    @abstractmethod
    def _bulk_index(self, index_name: str, docs: List[Dict[str, Any]]) -> None:
        ...

    @abstractmethod
    def _delete_indexes_internal(self, index_name: str) -> None:
        ...

    @abstractmethod
    def _delete_docs_internal(self, index_name: str, doc_ids: List[str]) -> int:
        ...

    @abstractmethod
    def _search_by_terms(
        self, index_name: str, field: str, values: List[str], size: int
    ) -> List[Dict[str, Any]]:
        ...

    @abstractmethod
    def _delete_or_detach_by_passage_ids(
        self,
        index_name: str,
        docs: List[Dict[str, Any]],
        deleted_passage_ids: List[str],
    ) -> Tuple[List[str], List[str]]:
        ...

    @abstractmethod
    def _detach_relation_ids_from_entities(self, relation_ids: List[str]) -> None:
        ...
