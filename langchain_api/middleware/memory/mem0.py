from langchain.agents.middleware import AgentMiddleware
from langchain.tools import ToolRuntime, tool
from mem0 import Memory
from mem0.configs.base import MemoryConfig, VectorStoreConfig, LlmConfig, EmbedderConfig
from mem0.configs.vector_stores.elasticsearch import ElasticsearchConfig
from mem0.configs.llms.openai import OpenAIConfig
from mem0.configs.embeddings.base import BaseEmbedderConfig
from settings import settings

host = settings.ES_URL.split("://")[1].split(":")[0]
port = int(settings.ES_URL.split(":")[1])
config = MemoryConfig(
    vector_store=VectorStoreConfig(
        provider="elasticsearch",
        config=ElasticsearchConfig(
            collection_name="mem0",
            host=host,
            port=port,
            embedding_model_dims=1024,
            user=settings.ES_URSR,
            password=settings.ES_PWD,
        ),
    ),
    llm=LlmConfig(
        provider="openai",
        config=OpenAIConfig(
            model=settings.CHAT_MODEL_NAME,
            api_key=settings.OPENAI_API_KEY,
            openai_base_url=settings.OPENAI_API_BASE,
            max_tokens=9000,
        ),
    ),
    embedder=EmbedderConfig(
        provider="openai",
        config=BaseEmbedderConfig(
            model=settings.EMBEDDING_MODEL_NAME,
            api_key=settings.OPENAI_API_KEY,
            openai_base_url=settings.OPENAI_API_BASE,
        ),
    ),
)
memory = Memory(config)


@tool
def memory_search(query: str, runtime: ToolRuntime) -> str:
    """从内存中搜索与查询相关的文档"""
    user_id = runtime.context.user_id
    relevant_memories = memory.search(
        query=query, filters={"user_id": user_id}, top_k=3
    )
    memories_str = "\n".join(
        f"- {entry['memory']}" for entry in relevant_memories["results"]
    )
    return memories_str


class Mem0Middleware(AgentMiddleware):
    def __init__(self, memory: Memory):
        self.memory = memory

    def aafter_model(self, state, runtime):
        # TODO 暂未实现
        pass
