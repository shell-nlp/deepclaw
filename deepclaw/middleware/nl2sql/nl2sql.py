import os
import re
from urllib.parse import urlparse

import psycopg
from langchain.agents.middleware import AgentMiddleware
from langchain.tools import tool
from langchain_core.messages import ToolMessage
from loguru import logger
from pydantic import Field

from deepclaw.agents.general.context import AgentContext
from deepclaw.middleware.nl2sql.ddl import fetch_schema_ddl
from deepclaw.middleware.nl2sql.ddl.oracle import (
    init_oracle_thick_client,
    parse_oracle_url,
)
from deepclaw.settings import settings

try:
    import oracledb
except ImportError:
    oracledb = None  # type: ignore[assignment]


ORACLE_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_$#]*$")


def _resolve_database_url() -> str | None:
    """解析 NL2SQL 目标库连接串。"""
    return os.getenv("NL2SQL_DATABASE_URL") or settings.PG_DATABASE_URL


def _resolve_schema(schema: str | None = None) -> str | None:
    """解析 NL2SQL 要使用的 schema。

    Args:
        schema: 显式传入的 schema 名称。
    """
    return schema or os.getenv("NL2SQL_SCHEMA") or None


def _normalize_oracle_schema(schema: str) -> str:
    """校验并规范化 Oracle schema 名称。

    Args:
        schema: 待校验的 schema 名称。
    """
    normalized_schema = schema.strip()
    if not ORACLE_IDENTIFIER_PATTERN.fullmatch(normalized_schema):
        raise ValueError(f"非法的 Oracle schema 名称: {schema}")
    return normalized_schema.upper()


def _apply_schema_to_connection(conn, database_url: str, schema: str | None) -> None:
    """在数据库连接上应用 schema 上下文。

    Args:
        conn: 已创建的数据库连接对象。
        database_url: 目标数据库连接串。
        schema: 需要切换到的 schema 名称。
    """
    if not schema:
        return
    scheme = urlparse(database_url).scheme.split("+", 1)[0]
    if scheme != "oracle":
        return
    normalized_schema = _normalize_oracle_schema(schema)
    with conn.cursor() as cur:
        cur.execute(f"ALTER SESSION SET CURRENT_SCHEMA = {normalized_schema}")


def _make_connection(database_url: str):
    """根据 URL scheme 自动选择数据库驱动并创建连接。"""
    scheme = urlparse(database_url).scheme.split("+", 1)[0]
    if scheme in ("postgresql", "postgres"):
        return psycopg.connect(database_url)
    if scheme == "oracle":
        if oracledb is None:
            raise RuntimeError(
                "oracledb 未安装，请执行: uv sync --extra oracle"
            )
        kwargs = parse_oracle_url(database_url)
        try:
            return oracledb.connect(**kwargs)
        except oracledb.Error as exc:
            if "DPY-3010" not in str(exc):
                raise
            logger.info("Oracle thin 模式不支持该服务器版本，尝试 thick 模式")
            return _make_oracle_connection_thick(**kwargs)
    raise ValueError(f"不支持的数据库类型: {scheme}")


def _make_oracle_connection_thick(**kwargs):
    """使用 thick 模式创建 Oracle 连接。"""
    try:
        init_oracle_thick_client()
    except Exception as init_exc:
        raise RuntimeError(
            "Oracle thick 模式初始化失败，请安装 Oracle Instant Client 并设置 ORACLE_CLIENT_LIB_DIR。"
            " 参考: https://python-oracledb.readthedocs.io/en/latest/user_guide/initialization.html\n"
            f"错误: {init_exc}"
        ) from init_exc
    return oracledb.connect(**kwargs)


class NL2SQLMiddleware(AgentMiddleware[None, AgentContext, None]):
    def get_user_ddl(self, user_id: str | None = None, schema: str | None = None) -> str:
        """获取用户数据库表的 DDL。

        Args:
            user_id: 用户标识，当前仅保留扩展位。
            schema: 显式指定的 schema 名称。
        """
        database_url = _resolve_database_url()
        resolved_schema = _resolve_schema(schema)
        logger.info(f"database_url: {database_url}")
        if not database_url:
            return "-- 未配置数据库连接（NL2SQL_DATABASE_URL / PG_DATABASE_URL）"

        # 后续可按 user_id 解析授权表列表并传入 table_names
        _ = user_id
        return fetch_schema_ddl(database_url, schema=resolved_schema)

    def get_run_sql_tool(self, user_id: str | None = None, schema: str | None = None):
        """构建执行 SQL 的工具。

        Args:
            user_id: 用户标识，当前仅保留扩展位。
            schema: 显式指定的 schema 名称。
        """
        resolved_schema = _resolve_schema(schema)
        user_ddl = self.get_user_ddl(user_id, schema=resolved_schema)

        @tool(description=f"用于运行sql语句，用户数据库表DDL如下: \n{user_ddl}")
        def run_sql(sql: str = Field(description="SQL 语句")) -> str:
            """运行 SQL 语句"""
            database_url = _resolve_database_url()
            if not database_url:
                return "错误：未配置数据库连接"

            try:
                with _make_connection(database_url) as conn:
                    _apply_schema_to_connection(conn, database_url, resolved_schema)
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
