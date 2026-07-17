from typing import Literal

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

    # openAI api_base 和 api_key配置
    OPENAI_API_BASE: str
    CHAT_MODEL_NAME: str

    # Chat模型配置
    OPENAI_API_KEY: str

    # Embedding模型配置
    EMBEDDING_MODEL_NAME: str

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
    VECTOR_STORE_BACKEND: Literal["elasticsearch", "pgsql"] = "elasticsearch"
    LANGSMITH_API_KEY: str | None = None

    # 是否使用copilotkit 的ag-ui 组件供前端使用
    USE_COPILOTKIT: bool = False

    # 是否支持工具搜索功能,（与 Claude Code 保持一致）
    USE_TOOL_SEARCH: bool = False
    # opensandbox 配置
    OPEN_SANDBOX_CODE_INTERPRETER_IMAGE: str = (
        "sandbox-registry.cn-zhangjiakou.cr.aliyuncs.com/opensandbox/code-interpreter:v1.0.2"
    )

    AUTH_ADMIN_EMAIL: str | None = None
    AUTH_ADMIN_PASSWORD: str | None = None
    AUTH_TOKEN_EXPIRE_DAYS: int = 1

    # 图表公网访问地址前缀，例如 https://example.com；为空时返回相对路径 /charts/xxx.png
    CHART_PUBLIC_URL: str = ""
    # 图表文件保留时长和数量上限，避免共享工作区无限增长
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
