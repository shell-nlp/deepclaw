"""验证 retrieve_context 按 state.index_names 选择检索范围。"""

from __future__ import annotations

from types import SimpleNamespace

from deepclaw.settings import settings
from deepclaw.tools import retriever


class FakeVectorStore:
    """记录 RRF 检索入参并返回预设结果的向量库替身。"""

    def __init__(self, docs: list[dict]) -> None:
        """保存预设检索结果。

        Args:
            docs: retrieve_with_rrf 的返回值。
        """
        self.docs = docs
        self.calls: list[dict] = []

    def retrieve_with_rrf(self, **kwargs) -> list[dict]:
        """记录检索入参并返回预设结果。

        Args:
            **kwargs: retrieve_with_rrf 的调用参数。

        Returns:
            预设的检索结果。
        """
        self.calls.append(kwargs)
        return self.docs


def _runtime(state: dict) -> SimpleNamespace:
    """构造只携带图状态的工具运行时替身。

    Args:
        state: 当前图状态。

    Returns:
        带 state 属性的运行时替身。
    """
    return SimpleNamespace(state=state)


def test_retrieve_context_uses_deduplicated_state_index_names(monkeypatch) -> None:
    """检索应使用 state.index_names（去重）并按线上参数排除停用切片。"""
    store = FakeVectorStore([{"content": "切片内容"}])
    monkeypatch.setattr(retriever, "get_default_retriever", lambda: store)

    result = retriever.retrieve_context.func(
        query="灌溉方式",
        runtime=_runtime(
            {"index_names": ["kb_a_passages", "kb_a_passages", "kb_b_passages"]}
        ),
    )

    assert result == "文档 1: \n切片内容"
    assert store.calls == [
        {
            "query": "灌溉方式",
            "k": settings.RAG_TOP_K,
            "index_names": ["kb_a_passages", "kb_b_passages"],
            "filter_conditions": {"metadata.state": {"$ne": False}},
        }
    ]


def test_retrieve_context_skips_retrieval_without_selected_knowledge_base(
    monkeypatch,
) -> None:
    """未选中任何知识库时不应触发检索。"""
    store = FakeVectorStore([{"content": "切片内容"}])
    monkeypatch.setattr(retriever, "get_default_retriever", lambda: store)

    result = retriever.retrieve_context.func(
        query="灌溉方式",
        runtime=_runtime({"index_names": []}),
    )

    assert result == "未选择知识库，本次未执行检索。"
    assert store.calls == []


def test_retrieve_context_reports_empty_result(monkeypatch) -> None:
    """检索结果为空时应返回明确的未命中提示。"""
    store = FakeVectorStore([])
    monkeypatch.setattr(retriever, "get_default_retriever", lambda: store)

    result = retriever.retrieve_context.func(
        query="灌溉方式",
        runtime=_runtime({"index_names": ["kb_a_passages"]}),
    )

    assert result == "未检索到相关知识库内容。"
