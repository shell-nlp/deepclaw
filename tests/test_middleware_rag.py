from langchain_core.messages import AIMessage, HumanMessage

from deepclaw.common.vector_store.base import AbstractVectorStore
from deepclaw.middleware import rag as rag_module
from deepclaw.middleware.rag import RAGMiddleware


class DummyVectorStore:
    """记录 RRF 混合检索调用的向量库替身。"""

    def __init__(self):
        self.rrf_calls = []

    def retrieve_with_rrf(self, query, k=3, index_names=None, filter_conditions=None):
        """记录调用并返回固定的混合检索结果。

        Args:
            query: 查询文本。
            k: 召回数量。
            index_names: 目标索引列表。
            filter_conditions: 元数据过滤条件。
        """
        self.rrf_calls.append({
            "query": query,
            "k": k,
            "index_names": index_names,
            "filter_conditions": filter_conditions,
        })
        return [
            {
                "content": "rrf result",
                "metadata": {"source": "hybrid"},
                "score": 0.5,
            }
        ]


def test_rag_retrieval_uses_hybrid_rrf():
    """RAG 检索统一走 BM25 + 向量的 RRF 混合检索。"""
    store = DummyVectorStore()
    middleware = RAGMiddleware(store)

    results = middleware._get_retrieve_result(
        query="hello",
        index_names=["kb_demo_passages"],
        k=2,
    )

    assert store.rrf_calls == [
        {
            "query": "hello",
            "k": 2,
            "index_names": ["kb_demo_passages"],
            "filter_conditions": {"metadata.state": {"$ne": False}},
        }
    ]
    assert results[0][0].page_content == "rrf result"
    assert results[0][0].metadata == {"source": "hybrid"}
    assert results[0][1] == 0.5


def test_rag_index_names_dedupe_and_drop_blank():
    """state 中的 index_names 会去重并丢弃空值。"""
    middleware = RAGMiddleware(DummyVectorStore())
    state = {
        "index_names": ["kb_a_passages", "kb_b_passages", "kb_a_passages", ""],
    }

    assert middleware._get_index_names(state) == [
        "kb_a_passages",
        "kb_b_passages",
    ]


def test_rag_index_names_requires_state():
    """缺少 index_names 时应直接报错，不再回退到单个索引。"""
    middleware = RAGMiddleware(DummyVectorStore())

    try:
        middleware._get_index_names({})
    except ValueError as exc:
        assert "index_names" in str(exc)
    else:  # pragma: no cover - 仅用于断言必须抛错
        raise AssertionError("缺少 index_names 时应抛出 ValueError")


def test_merge_results_rrf_ranks_shared_documents_first():
    """RRF 让两个召回列表共同命中的文档排到最前。"""
    vector_results = [
        {"id": "a", "content": "A"},
        {"id": "b", "content": "B"},
    ]
    keyword_results = [
        {"id": "c", "content": "C"},
        {"id": "b", "content": "B"},
    ]

    merged = AbstractVectorStore.merge_results_rrf(
        vector_results=vector_results,
        keyword_results=keyword_results,
        k=3,
    )

    assert [item["id"] for item in merged] == ["b", "a", "c"]


def test_merge_results_rrf_interleaves_disjoint_lists():
    """两路候选完全不重合时必须交替取，否则 BM25 结果会被整段丢掉。"""
    vector_results = [{"id": f"v{index}"} for index in range(1, 6)]
    keyword_results = [{"id": f"k{index}"} for index in range(1, 6)]

    merged = AbstractVectorStore.merge_results_rrf(
        vector_results=vector_results,
        keyword_results=keyword_results,
        k=6,
    )

    assert [item["id"] for item in merged] == ["v1", "k1", "v2", "k2", "v3", "k3"]


class RecordingRewriteModel:
    """记录 config 的问题改写模型替身。"""

    def __init__(self):
        self.configs: list[dict] = []

    def bind(self, **kwargs):
        """忽略绑定参数，返回自身。

        Args:
            kwargs: 绑定参数。
        """
        return self

    def invoke(self, prompt, config=None):
        """记录调用配置并返回改写结果。

        Args:
            prompt: 提示词。
            config: 调用配置。
        """
        self.configs.append(config or {})
        return AIMessage(content="改写后的问题")


class RecordingRouterModel:
    """记录 config 的检索路由模型替身。"""

    def __init__(self):
        self.configs: list[dict] = []

    def with_structured_output(self, schema=None, method=None):
        """忽略结构化参数，返回自身。

        Args:
            schema: 结构化输出模型。
            method: 结构化输出方式。
        """
        return self

    def bind(self, **kwargs):
        """忽略绑定参数，返回自身。

        Args:
            kwargs: 绑定参数。
        """
        return self

    def invoke(self, messages, config=None):
        """记录调用配置并返回路由结果。

        Args:
            messages: 提示消息列表。
            config: 调用配置。
        """
        self.configs.append(config or {})
        return {"原因": "日常问候", "路由": "LLM"}


def test_internal_model_calls_do_not_emit_stream_events():
    """改写与路由的内部模型调用必须清空 callbacks，避免正文被污染。"""
    rewrite_model = RecordingRewriteModel()
    rewrite_middleware = RAGMiddleware(
        DummyVectorStore(), rewrite_query=True, model=rewrite_model
    )
    rewritten = rewrite_middleware._get_rewrite_query([HumanMessage(content="你好")])

    router_model = RecordingRouterModel()
    router_middleware = RAGMiddleware(
        DummyVectorStore(), retrieve_router=True, model=router_model
    )
    route = router_middleware._retrieve_router([HumanMessage(content="你好")])

    assert rewritten == "改写后的问题"
    assert route == "LLM"
    assert rewrite_model.configs[0]["callbacks"] == []
    assert rewrite_model.configs[0]["tags"] == ["rag_internal"]
    assert router_model.configs[0]["callbacks"] == []
    assert router_model.configs[0]["tags"] == ["rag_internal"]


def test_before_model_retrieves_with_configured_top_k(monkeypatch):
    """真实 Runtime 没有 state 属性，检索参数必须来自 state 与 RAG_TOP_K。"""
    store = DummyVectorStore()
    middleware = RAGMiddleware(store)
    monkeypatch.setattr(rag_module.settings, "RAG_TOP_K", 7)

    class RuntimeWithoutState:
        """刻意不提供 state 属性，复现 langgraph Runtime 的真实形态。"""

    state = {
        "messages": [HumanMessage(content="公司馈赠行为准则")],
        "index_names": ["kb_a_passages"],
    }

    result = middleware.before_model(state, RuntimeWithoutState())

    assert store.rrf_calls == [
        {
            "query": "公司馈赠行为准则",
            "k": 7,
            "index_names": ["kb_a_passages"],
            "filter_conditions": {"metadata.state": {"$ne": False}},
        }
    ]
    assert [doc.page_content for doc in result["docs"]] == ["rrf result"]
