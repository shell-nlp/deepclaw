import os

from langchain.agents.middleware import AgentMiddleware
from langchain.tools import tool
from loguru import logger
from pydantic import Field

from deepclaw.agents.general.context import AgentContext
from deepclaw.middleware.nl2sql.ddl import fetch_schema_ddl
from deepclaw.settings import settings

DATABASE_URL = "postgresql://admin:admin@localhost:5432/langchain_api"


def _resolve_database_url() -> str | None:
    """解析 NL2SQL 目标库连接串。"""
    return os.getenv("NL2SQL_DATABASE_URL") or settings.PG_DATABASE_URL or DATABASE_URL


class BusinessMiddleware(AgentMiddleware[None, AgentContext, None]):
    def get_user_ddl(self, user_id: str | None = None) -> str:
        """获取用户数据库表的 DDL。"""
        database_url = _resolve_database_url()
        logger.info(f"database_url: {database_url}")
        if not database_url:
            return "-- 未配置数据库连接（NL2SQL_DATABASE_URL / PG_DATABASE_URL）"

        # 后续可按 user_id 解析授权表列表并传入 table_names
        _ = user_id
        return fetch_schema_ddl(database_url)

    def wrap_model_call(self, request, handler):
        context: AgentContext = request.runtime.context
        user_id = context.user_id
        user_ddl = self.get_user_ddl(user_id)

        @tool(description=f"用于运行sql语句，用户数据库表DDL如下: \n{user_ddl}", name="run_sql")
        def run_sql(sql: str = Field(description="SQL 语句")) -> str:
            """运行 SQL 语句"""
            return "SQL 语句运行成功"


if __name__ == "__main__":
    middleware = BusinessMiddleware()
    print(middleware.get_user_ddl())
