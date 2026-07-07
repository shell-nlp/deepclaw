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
from deepclaw.middleware.nl2sql.ddl import fetch_schema_ddl, list_tables
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


_READONLY_PREFIX_RE: re.Pattern[str] = re.compile(
    r"^\s*(?:SELECT|WITH|EXPLAIN|SHOW|DESC(?:RIBE)?)\b",
    re.IGNORECASE,
)


def _strip_leading_sql_comments(sql: str) -> str:
    """移除 SQL 开头连续出现的空白和注释。

    Args:
        sql: 原始 SQL 文本。
    """
    return re.sub(r"^\s*(?:(?:--[^\n]*(?:\n|$))|(?:/\*.*?\*/\s*))*", "", sql, flags=re.DOTALL)


def _validate_readonly(sql: str) -> None:
    """校验 SQL 语句是否为只读查询，拒绝写入/修改操作。

    Args:
        sql: 待执行的 SQL 语句。

    Raises:
        ValueError: 当 SQL 为非查询语句时抛出。
    """
    normalized_sql = _strip_leading_sql_comments(sql)
    if not _READONLY_PREFIX_RE.match(normalized_sql):
        raise ValueError(f"仅允许执行查询（SELECT）语句，拒绝写入/修改操作: {sql}")


def _make_connection(database_url: str):
    """根据 URL scheme 自动选择数据库驱动并创建连接。"""
    scheme = urlparse(database_url).scheme.split("+", 1)[0]
    if scheme in ("postgresql", "postgres"):
        return psycopg.connect(database_url)
    if scheme == "oracle":
        if oracledb is None:
            raise RuntimeError("oracledb 未安装，请执行: uv sync --extra oracle")
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

    def get_list_tables_tool(self, user_id: str | None = None, schema: str | None = None):
        """构建列出数据库中所有表的工具。

        Args:
            user_id: 用户标识，当前仅保留扩展位。
            schema: 显式指定的 schema 名称。
        """
        resolved_schema = _resolve_schema(schema)

        @tool(description="列出当前数据库中所有可用的表名")
        def list_tables_tool() -> str:
            """列出数据库中所有可用的表名"""
            database_url = _resolve_database_url()
            if not database_url:
                return "未配置数据库连接（NL2SQL_DATABASE_URL / PG_DATABASE_URL）"
            try:
                tables = list_tables(database_url, schema=resolved_schema)
                if not tables:
                    return "数据库中未找到数据表"
                return "数据库中的表:\n" + "\n".join(f"- {t}" for t in tables)
            except Exception as exc:
                return f"获取表列表失败：{exc}"

        return list_tables_tool

    def get_describe_tables_tool(self, user_id: str | None = None, schema: str | None = None):
        """构建查看指定表 DDL 的工具，复用 fetch_schema_ddl 逻辑。

        Args:
            user_id: 用户标识，当前仅保留扩展位。
            schema: 显式指定的 schema 名称。
        """
        resolved_schema = _resolve_schema(schema)

        @tool
        def describe_tables_tool(
            table_names: str = Field(description="表名，多个表用逗号分隔，支持 schema.table_name 格式指定模式,未指定 schema 时使用默认的schema"),
        ) -> str:
            """查看指定数据库表的详细 DDL 结构（列名、类型、主键、注释等），支持同时查看多张表.
            ## 要求
            - 输入参数 table_names 为表名，多个表用逗号分隔。
            - 支持 schema.table_name 格式显式指定模式，未指定 schema 时使用默认的schema。
            """
            database_url = _resolve_database_url()
            if not database_url:
                return "未配置数据库连接（NL2SQL_DATABASE_URL / PG_DATABASE_URL）"
            raw_names = [name.strip() for name in table_names.split(",") if name.strip()]
            if not raw_names:
                return "请指定要查看的表名"

            # 按 schema 分组：schema.table_name 格式提取 schema，否则使用默认值
            schema_map: dict[str | None, list[str]] = {}
            for raw in raw_names:
                if "." in raw:
                    schema, tbl = raw.split(".", 1)
                    schema = schema.strip()
                    tbl = tbl.strip()
                    if tbl:
                        schema_map.setdefault(schema, []).append(tbl)
                else:
                    schema_map.setdefault(resolved_schema, []).append(raw)

            parts: list[str] = []
            for schema, names in schema_map.items():
                part = fetch_schema_ddl(database_url, table_names=names, schema=schema)
                if part:
                    parts.append(part)
            return "\n---\n".join(parts) if parts else ""

        return describe_tables_tool

    def get_run_sql_tool(self, user_id: str | None = None, schema: str | None = None):
        """构建执行 SQL 的工具。

        Args:
            user_id: 用户标识，当前仅保留扩展位。
            schema: 显式指定的 schema 名称。
        """
        resolved_schema = _resolve_schema(schema)
        # user_ddl = self.get_user_ddl(user_id, schema=resolved_schema)

        @tool
        def run_sql(sql: str = Field(description="SQL 语句")) -> str:
            """用于运行sql语句，你使用的数据库类型是 Oracle。
            # 必须遵守的要求：
            - 仅允许执行查询（SELECT）语句，拒绝写入/修改操作。
            - 禁止在 SQL 中添加任何注释（包括 -- 和 /* */ 注释），请直接输出可执行 SQL。
            - 在查询某个数据库表之前，如果不知道该表的 DDL 结构，必须先使用 describe_tables_tool 查看该表的 DDL 结构，禁止直接去查询表进行DDL结构探索。
            - 查询结果最多展示 30 行，超出部分会被截断并提示数据量过大，建议用 SQL运算或 聚合等操作，或者使用Python 代码处理。
            - 尽量使用简单的 SQL 语句 + 多次查询，避免使用复杂的查询逻辑（因为模型能力有限，负责SQL命令容易出错）。
            """
            database_url = _resolve_database_url()
            if not database_url:
                return "错误：未配置数据库连接"

            try:
                _validate_readonly(sql)
                with _make_connection(database_url) as conn:
                    _apply_schema_to_connection(conn, database_url, resolved_schema)
                    MAX_DISPLAY_ROWS = 30  # 最多展示 30 行
                    with conn.cursor() as cur:
                        cur.execute(sql)

                        # 判断是否有返回结果（SELECT 查询）
                        if cur.description:
                            columns = [desc[0] for desc in cur.description]
                            rows = cur.fetchmany(MAX_DISPLAY_ROWS + 1)

                            # 格式化为表格
                            result_lines = ["\t".join(columns)]
                            result_lines.append("-" * 80)
                            for row in rows[:MAX_DISPLAY_ROWS]:
                                result_lines.append("\t".join(str(v) for v in row))

                            if len(rows) > MAX_DISPLAY_ROWS:
                                result_lines.append("-" * 80)
                                result_lines.append(
                                    f"数据量过大，仅展示前 {MAX_DISPLAY_ROWS} 行（共 >{MAX_DISPLAY_ROWS} 行）。"
                                )
                                result_lines.append("建议用 SQL运算或 聚合等操作，或者使用Python代码处理后再返回。")

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
        list_tables_tool = self.get_list_tables_tool(context.user_id)
        describe_tables_tool = self.get_describe_tables_tool(context.user_id)
        new_tools = [*request.tools]
        new_tools.append(run_sql_tool)
        new_tools.append(list_tables_tool)
        new_tools.append(describe_tables_tool)
        return handler(request.override(tools=new_tools))

    async def awrap_model_call(self, request, handler):
        return await self.wrap_model_call(request, handler)

    async def awrap_tool_call(self, request, handler):
        tool_name = request.tool_call["name"]
        context: AgentContext = request.runtime.context
        if tool_name == "run_sql":
            run_sql_tool = self.get_run_sql_tool(context.user_id)
            result = await run_sql_tool.arun(request.tool_call["args"])
            return ToolMessage(content=result, tool_call_id=request.tool_call["id"])
        if tool_name == "list_tables_tool":
            list_tables_tool = self.get_list_tables_tool(context.user_id)
            result = await list_tables_tool.arun(request.tool_call["args"])
            return ToolMessage(content=result, tool_call_id=request.tool_call["id"])
        if tool_name == "describe_tables_tool":
            describe_tables_tool = self.get_describe_tables_tool(context.user_id)
            result = await describe_tables_tool.arun(request.tool_call["args"])
            return ToolMessage(content=result, tool_call_id=request.tool_call["id"])
        return await handler(request)


if __name__ == "__main__":
    middleware = NL2SQLMiddleware()
    with open("GISTOOLS_DDL.txt", "w") as f:
        f.write(middleware.get_user_ddl())
