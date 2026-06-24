import os

import psycopg
from langchain.agents.middleware import AgentMiddleware
from langchain.tools import tool
from langchain_core.messages import ToolMessage
from loguru import logger
from pydantic import Field

from deepclaw.agents.general.context import AgentContext
from deepclaw.middleware.nl2sql.ddl import fetch_schema_ddl
from deepclaw.settings import settings

DATABASE_URL = "postgresql://admin:admin@localhost:5432/langchain_api"


def _resolve_database_url() -> str | None:
    """解析 NL2SQL 目标库连接串。"""
    return os.getenv("NL2SQL_DATABASE_URL") or settings.PG_DATABASE_URL or DATABASE_URL


class NL2SQLMiddleware(AgentMiddleware[None, AgentContext, None]):
    def get_user_ddl(self, user_id: str | None = None) -> str:
        """获取用户数据库表的 DDL。"""
        database_url = _resolve_database_url()
        logger.info(f"database_url: {database_url}")
        if not database_url:
            return "-- 未配置数据库连接（NL2SQL_DATABASE_URL / PG_DATABASE_URL）"

        # 后续可按 user_id 解析授权表列表并传入 table_names
        _ = user_id
        return fetch_schema_ddl(database_url)

    def get_run_sql_tool(self, user_id: str | None = None):
        user_ddl = self.get_user_ddl(user_id)

        @tool(description=f"用于运行sql语句，用户数据库表DDL如下: \n{user_ddl}")
        def run_sql(sql: str = Field(description="SQL 语句")) -> str:
            """运行 SQL 语句"""
            database_url = _resolve_database_url()
            if not database_url:
                return "错误：未配置数据库连接"

            try:
                # 使用 psycopg 同步连接执行 SQL
                with psycopg.connect(database_url) as conn:
                    with conn.cursor() as cur:
                        cur.execute(sql)

                        # 判断是否有返回结果（SELECT 查询）
                        if cur.description:
                            columns = [desc[0] for desc in cur.description]
                            rows = cur.fetchall()

                            # 格式化为表格
                            result_lines = ["\t".join(columns)]
                            result_lines.append("-" * 80)
                            for row in rows:
                                result_lines.append("\t".join(str(v) for v in row))

                            return "\n".join(result_lines)
                        else:
                            # DML 操作（INSERT/UPDATE/DELETE）
                            conn.commit()
                            return f"SQL 执行成功，影响行数：{cur.rowcount}"

            except Exception as exc:
                logger.error(f"SQL 执行失败：{exc}")
                return f"SQL 执行失败：{exc}"

        return run_sql

    def wrap_model_call(self, request, handler):
        context: AgentContext = request.runtime.context
        run_sql_tool = self.get_run_sql_tool(context.user_id)

        ori_tools = request.tools
        new_tools = ori_tools + [run_sql_tool]
        return handler(request.override(tools=new_tools))

    async def awrap_model_call(self, request, handler):
        return await self.wrap_model_call(request, handler)

    async def awrap_tool_call(self, request, handler):
        tool_name = request.tool_call["name"]
        if tool_name == "run_sql":
            context: AgentContext = request.runtime.context
            run_sql_tool = self.get_run_sql_tool(context.user_id)
            result = await run_sql_tool.arun(request.tool_call["args"])
            return ToolMessage(content=result, tool_call_id=request.tool_call["id"])
        return await handler(request)


if __name__ == "__main__":
    middleware = NL2SQLMiddleware()
    print(middleware.get_user_ddl())
