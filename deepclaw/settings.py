from typing import Any, Literal

from dotenv import find_dotenv, load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# 获取.env文件路径（Docker 下 env 变量由 compose 注入，不需要 .env 文件）
env_path = find_dotenv(filename=".env", raise_error_if_not_found=False)

# 若存在 .env 文件，将其内容加载到环境变量中
if env_path:
    load_dotenv(env_path)


class Settings(BaseSettings):
    # 服务监听配置
    HOST: str = "0.0.0.0"
    PORT: int = 7869
    LOCAL_HOST: str = "http://localhost:7869"

    # openAI api_base 和 api_key配置；留空时由前端模型目录配置
    OPENAI_API_BASE: str = ""
    CHAT_MODEL_NAME: str = ""

    # Chat模型配置；留空时由前端模型目录配置
    OPENAI_API_KEY: str = ""
    # 模型上下文窗口长度，用于按 80% 阈值触发摘要；按实际部署模型调整。
    MODEL_CONTEXT_WINDOW: int = Field(default=128000, ge=1)

    # Embedding模型配置；留空时由前端模型目录配置
    EMBEDDING_MODEL_NAME: str = ""

    # elasticsearch配置
    ES_URL: str | None = None
    ES_URSR: str | None = None
    ES_PWD: str | None = None

    # Tavily API Key 配置
    TAVILY_API_KEY: str | None = None

    # 使用沙盒配置
    BACKEND_TYPE: Literal["local_shell", "store", "sandbox"] = "local_shell"

    # postgres数据库配置
    PG_DATABASE_URL: str | None = None
    SQLITE_DB_PATH: str | None = None
    # 默认 sqlite：单文件 sqlite-vec，无需任何中间件；也可选 pgsql / elasticsearch / none
    VECTOR_STORE_BACKEND: Literal["elasticsearch", "pgsql", "sqlite", "none"] = "sqlite"
    # sqlite-vec 数据库文件路径；留空时落在 HOME_PATH/vector.db
    SQLITE_VECTOR_DB_PATH: str | None = None
    LANGSMITH_API_KEY: str | None = None

    # 对象存储配置：默认本地，显式选择 minio 时才连接远端
    OBJECT_STORAGE_PROVIDER: Literal["local", "minio"] = "local"
    LOCAL_STORAGE_ROOT: str | None = None
    MINIO_ENDPOINT_URL: str | None = None
    MINIO_ACCESS_KEY: str | None = None
    MINIO_SECRET_KEY: str | None = None
    MINIO_SERVICE_ADDRESSES: str | None = None

    # 单个服务实例同时处理的知识文件数；PDF 解析和索引会占用 CPU 与模型服务。
    KNOWLEDGE_UPLOAD_WORKERS: int = Field(default=2, ge=1, le=8)

    # RAG 检索最终交给模型的切片数量；单路候选量为 max(RAG_TOP_K * 4, 20)。
    RAG_TOP_K: int = Field(default=15, ge=1, le=100)

    # 是否使用copilotkit 的ag-ui 组件供前端使用
    USE_COPILOTKIT: bool = False

    # 是否支持工具搜索功能,（与 Claude Code 保持一致）
    USE_TOOL_SEARCH: bool = False

    # MCP 服务配置。不同发布版本可通过环境变量 MCP_CONFIG 注入 JSON 配置。
    MCP_CONFIG: dict[str, Any] = Field(default_factory=dict)

    # AG-UI Run 存储与过期清理配置
    AGUI_RUN_RETENTION_SECONDS: int = Field(default=3600, ge=60)
    # Thread 元数据保留秒数；0 表示只允许用户显式删除，不自动过期。
    AGUI_THREAD_RETENTION_SECONDS: int = Field(default=0, ge=0)
    AGUI_RUN_MAX_EVENTS: int = Field(default=2000, ge=100)
    AGUI_RUN_CLEANUP_INTERVAL_SECONDS: int = Field(default=60, ge=10)
    AGUI_RUN_POLL_INTERVAL_SECONDS: float = Field(default=0.5, ge=0.1)


    # opensandbox 配置
    OPEN_SANDBOX_CODE_INTERPRETER_IMAGE: str = (
        "sandbox-registry.cn-zhangjiakou.cr.aliyuncs.com/opensandbox/code-interpreter:v1.0.2"
    )

    # RBAC 授权模型与策略文件；都留空时使用包内默认策略，配置时两者必须同时提供
    RBAC_MODEL_PATH: str = ""
    RBAC_POLICY_PATH: str = ""
    # 是否把策略存到数据库；关闭时直接读取策略文件
    RBAC_STORE_ENABLED: bool = True

    # 首次启动自举管理员：用户名/密码默认 deepclaw/deepclaw，邮箱可选
    AUTH_ADMIN_USERNAME: str = "deepclaw"
    AUTH_ADMIN_PASSWORD: str = "deepclaw"
    AUTH_ADMIN_EMAIL: str | None = None
    AUTH_TOKEN_EXPIRE_DAYS: int = 1
    # 是否开放公开注册；默认关闭，账号由管理员创建
    AUTH_ALLOW_REGISTRATION: bool = False
    # 是否允许未登录游客访问按归属隔离的接口；公网部署建议关闭
    ALLOW_GUEST_ACCESS: bool = True
    # 连续登录失败达到阈值后锁定账号的分钟数
    AUTH_LOGIN_MAX_ATTEMPTS: int = Field(default=5, ge=1)
    AUTH_LOGIN_LOCK_MINUTES: int = Field(default=15, ge=1)

    # 图表公网访问地址前缀，例如 https://example.com；为空时返回相对路径 /charts/xxx.png
    CHART_PUBLIC_URL: str = ""
    # 图表对象保留时长和数量上限，避免对象存储中的图表无限增长
    CHART_RETENTION_HOURS: int = Field(default=24, ge=1, le=720)
    CHART_MAX_FILES: int = Field(default=1_000, ge=1, le=10_000)

    model_config = SettingsConfigDict(
        env_file=env_path or None,
        env_file_encoding="utf-8",
        extra="ignore",  # 改为ignore，允许额外环境变量
    )


def get_settings() -> Settings:
    return Settings()


settings = get_settings()

if __name__ == "__main__":
    print(settings.CHAT_MODEL_NAME)
