"""验证向量检索与知识库服务采用惰性初始化。"""

from __future__ import annotations


def test_default_retriever_is_created_on_first_use(monkeypatch) -> None:
    """默认检索器在首次调用前不创建向量库。

    Args:
        monkeypatch: pytest 提供的对象替换工具。
    """
    from deepclaw.tools import retriever

    calls: list[dict[str, object]] = []
    fake_model = object()
    fake_store = object()

    monkeypatch.setattr(retriever, "default_retriever", None)
    monkeypatch.setattr(retriever, "get_embedding_model", lambda: fake_model)
    monkeypatch.setattr(
        retriever,
        "create_default_vector_store",
        lambda **kwargs: calls.append(kwargs) or fake_store,
    )

    assert calls == []
    assert retriever.get_default_retriever() is fake_store
    assert calls == [{"embedding_model": fake_model}]


def test_knowledge_base_manager_is_created_on_first_use(monkeypatch) -> None:
    """知识库管理器在首次调用前不创建向量库。

    Args:
        monkeypatch: pytest 提供的对象替换工具。
    """
    from deepclaw.web_backend.knowledge_bases import service

    calls: list[dict[str, object]] = []
    fake_model = object()

    class FakeManager:
        """记录知识库管理器构造参数的替身。"""

        def __init__(self, vector_store, object_storage=None) -> None:
            """保存构造参数。

            Args:
                vector_store: 向量存储。
                object_storage: 对象存储。
            """
            self.vector_store = vector_store
            self.object_storage = object_storage

    fake_store = object()
    monkeypatch.setattr(service, "knowledge_base_manager", None)
    monkeypatch.setattr(service, "get_embedding_model", lambda: fake_model)
    monkeypatch.setattr(
        service,
        "create_default_vector_store",
        lambda **kwargs: calls.append(kwargs) or fake_store,
    )
    monkeypatch.setattr(service, "KnowledgeBaseManager", FakeManager)

    assert calls == []
    manager = service.get_knowledge_base_manager()
    assert manager.vector_store is fake_store
    assert calls == [{"embedding_model": fake_model}]
