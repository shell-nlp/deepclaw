import os
import re
from urllib.parse import urlparse

import psycopg
from langchain.agents.middleware import AgentMiddleware
from langchain.tools import BaseTool, tool
from langchain_core.messages import ToolMessage
from loguru import logger
from pydantic import Field

from deepclaw.agents.general.context import AgentContext
from deepclaw.middleware.nl2sql.ddl import fetch_schema_ddl, list_tables
from deepclaw.settings import settings

try:
    import oracledb
except ImportError:
    oracledb = None  # type: ignore[assignment]


ORACLE_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_$#]*$")
# True：简版。字段注释内联在字段定义末尾,False：完整版。保留独立注释语句
DESCRIBE_TABLES_INLINE_COLUMN_COMMENTS = True

_COLUMN_COMMENT_DDL_RE = re.compile(
    r'COMMENT ON COLUMN "(?P<table>[^"]+)"\."(?P<column>[^"]+)" IS '
    r"'(?P<comment>(?:''|[^'])*)';"
)


def _inline_column_comments(ddl: str) -> str:
    """将字段注释内联到 describe_tables_tool 返回的列定义中。

    Args:
        ddl: 由 DDL 拉取器生成的原始 DDL 文本。
    """
    comments_by_table: dict[str, list[tuple[str, str]]] = {}
    for match in _COLUMN_COMMENT_DDL_RE.finditer(ddl):
        comments_by_table.setdefault(match["table"], []).append((match["column"], match["comment"].replace("''", "'")))

    inlined_columns: set[tuple[str, str]] = set()
    result = ddl
    for table_name, column_comments in comments_by_table.items():
        table_ddl_re = re.compile(
            rf'(?P<prefix>CREATE TABLE "{re.escape(table_name)}" \(\n)'
            r"(?P<columns>.*?)"
            r"(?P<suffix>\n\);)",
            re.DOTALL,
        )

        def append_comments(match: re.Match[str]) -> str:
            """在当前表的字段定义末尾追加字段注释。

            Args:
                match: 当前 CREATE TABLE 语句的正则匹配结果。
            """
            columns = match["columns"]
            for column_name, comment in column_comments:
                column_re = re.compile(
                    rf'(?m)^(?P<definition>[ \t]*"{re.escape(column_name)}"'
                    r"[^\n]*?)(?P<separator>,?)$"
                )
                safe_comment = comment.replace("*/", "* /")
                columns, count = column_re.subn(
                    lambda column_match: (
                        f"{column_match['definition']} /* {safe_comment} */{column_match['separator']}"
                    ),
                    columns,
                    count=1,
                )
                if count:
                    inlined_columns.add((table_name, column_name))
            return f"{match['prefix']}{columns}{match['suffix']}"

        result = table_ddl_re.sub(append_comments, result, count=1)

    result = _COLUMN_COMMENT_DDL_RE.sub(
        lambda match: "" if (match["table"], match["column"]) in inlined_columns else match[0],
        result,
    )
    return re.sub(r"\n{3,}", "\n\n", result)


def _resolve_database_url() -> str | None:
    """解析 NL2SQL 目标库连接串。"""
    return os.getenv("NL2SQL_DATABASE_URL") or settings.PG_DATABASE_URL


def _resolve_schema(schema: str | None = None) -> str | None:
    """解析 NL2SQL 要使用的 schema。

    Args:
        schema: 显式传入的 schema 名称。
    """
    return schema or os.getenv("NL2SQL_SCHEMA") or None


def _resolve_allowed_tables(allowed_tables: list[str] | None = None) -> list[str] | None:
    """解析 NL2SQL 可访问表白名单。

    未配置或为空时返回 None，表示允许访问全部表。
    配置来源优先级：显式参数 > 环境变量 NL2SQL_ALLOWED_TABLES（逗号分隔）。

    Args:
        allowed_tables: 显式传入的可访问表名列表。
    """
    if allowed_tables is not None:
        tables = [name.strip() for name in allowed_tables if name and str(name).strip()]
        return tables or None

    raw = os.getenv("NL2SQL_ALLOWED_TABLES")
    if not raw or not raw.strip():
        return None
    tables = [name.strip() for name in raw.split(",") if name.strip()]
    return tables or None


def _normalize_table_key(table_name: str) -> str:
    """规范化表名用于白名单比较（去引号、去 schema、大写）。

    Args:
        table_name: 原始表名，支持 schema.table 与带引号形式。
    """
    name = table_name.strip().replace('"', "").replace("`", "")
    if "." in name:
        name = name.rsplit(".", 1)[-1]
    return name.upper()


def _is_table_allowed(table_name: str, allowed_tables: list[str] | None) -> bool:
    """判断表名是否在可访问白名单内。

    Args:
        table_name: 待检查的表名。
        allowed_tables: 白名单；None 表示允许全部。
    """
    if allowed_tables is None:
        return True
    target = _normalize_table_key(table_name)
    allowed_keys = {_normalize_table_key(name) for name in allowed_tables}
    return target in allowed_keys


def _filter_allowed_tables(table_names: list[str], allowed_tables: list[str] | None) -> list[str]:
    """按白名单过滤表名列表。

    Args:
        table_names: 原始表名列表。
        allowed_tables: 白名单；None 表示不过滤。
    """
    if allowed_tables is None:
        return table_names
    return [name for name in table_names if _is_table_allowed(name, allowed_tables)]


def _reject_disallowed_tables(table_names: list[str], allowed_tables: list[str] | None) -> list[str]:
    """校验请求的表是否全部在白名单内，返回不合法表名列表。

    Args:
        table_names: 请求访问的表名列表。
        allowed_tables: 白名单；None 表示全部允许。
    """
    if allowed_tables is None:
        return []
    return [name for name in table_names if not _is_table_allowed(name, allowed_tables)]


_SQL_TABLE_REF_RE = re.compile(
    r"""\b(?:FROM|JOIN)\s+
        (?:"?(?P<schema>[A-Za-z][A-Za-z0-9_$#]*)"?\s*\.\s*)?
        "?(?P<table>[A-Za-z][A-Za-z0-9_$#]*)"?
    """,
    re.IGNORECASE | re.VERBOSE,
)


def _extract_sql_table_refs(sql: str) -> list[str]:
    """从 SQL 中粗粒度提取 FROM/JOIN 引用的表名。

    Args:
        sql: 待分析的 SQL 文本。
    """
    normalized_sql = _strip_leading_sql_comments(sql)
    refs: list[str] = []
    seen: set[str] = set()
    for match in _SQL_TABLE_REF_RE.finditer(normalized_sql):
        table = match.group("table")
        if not table:
            continue
        key = _normalize_table_key(table)
        if key in seen:
            continue
        seen.add(key)
        refs.append(table)
    return refs


def _validate_sql_tables_allowed(sql: str, allowed_tables: list[str] | None) -> None:
    """校验 SQL 引用的表是否均在可访问白名单内。

    Args:
        sql: 待执行的 SQL。
        allowed_tables: 白名单；None 表示允许全部。

    Raises:
        ValueError: 当 SQL 引用了未授权表时抛出。
    """
    if allowed_tables is None:
        return
    refs = _extract_sql_table_refs(sql)
    denied = _reject_disallowed_tables(refs, allowed_tables)
    if denied:
        denied_text = ", ".join(denied)
        allowed_text = ", ".join(allowed_tables)
        raise ValueError(f"仅允许访问配置的表，拒绝访问: {denied_text}；可访问表: {allowed_text}")


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
_DATA_QUERY_PREFIX_RE: re.Pattern[str] = re.compile(
    r"^\s*(?:SELECT|WITH)\b",
    re.IGNORECASE,
)
MAX_DISPLAY_ROWS = 30


def _get_database_scheme(database_url: str) -> str:
    """从数据库连接串解析 scheme。

    Args:
        database_url: 目标数据库连接串。
    """
    return urlparse(database_url).scheme.split("+", 1)[0]


def _apply_row_limit(sql: str, max_rows: int, scheme: str) -> str:
    """在 SQL 层限制查询最多返回的行数，避免大结果集压垮数据库。

    对 SELECT/WITH 查询统一外包一层子查询并按数据库方言加行数限制；
    EXPLAIN/SHOW/DESCRIBE 等元数据语句原样返回。

    Args:
        sql: 原始 SQL 语句。
        max_rows: 允许数据库最多返回的行数。
        scheme: 数据库 scheme，如 postgresql / oracle。
    """
    if max_rows <= 0:
        return sql

    normalized_sql = _strip_leading_sql_comments(sql)
    if not _DATA_QUERY_PREFIX_RE.match(normalized_sql):
        return sql

    limited_sql = sql.strip().rstrip(";")
    if scheme in ("postgresql", "postgres"):
        return f"SELECT * FROM (\n{limited_sql}\n) AS _nl2sql_row_limit LIMIT {max_rows}"
    if scheme == "oracle":
        clean_sql = normalized_sql.strip().rstrip(";")
        return f"SELECT * FROM (\n{clean_sql}\n) nl2sql_row_limit WHERE ROWNUM <= {max_rows}"
    return f"SELECT * FROM (\n{limited_sql}\n) AS _nl2sql_row_limit FETCH FIRST {max_rows} ROWS ONLY"


def _inject_filters(sql: str, filters: list[str]) -> str:
    """向 SQL 语句注入额外的 WHERE 过滤条件列表（追加到最外层 WHERE/末尾）。

    每个过滤条件以 AND 连接。自动处理已有 WHERE 和无 WHERE 两种情况，
    子查询中的关键字不受影响。

    Args:
        sql: 原始 SQL 语句。
        filters: 过滤条件表达式列表，每个元素为一个完整的 WHERE 子句条件。

    Returns:
        注入过滤条件后的 SQL。
    """
    if not filters:
        return sql

    sql = sql.strip().rstrip(";")
    upper = sql.upper()

    def _find_outer_keyword(keyword: str, start: int = 0) -> int:
        depth = 0
        in_single = False
        in_double = False
        klen = len(keyword)
        for i in range(start, len(sql)):
            ch = sql[i]
            if ch == "'" and not in_double:
                in_single = not in_single
            elif ch == '"' and not in_single:
                in_double = not in_double
            elif not in_single and not in_double:
                if ch == '(':
                    depth += 1
                elif ch == ')':
                    depth -= 1
                elif depth == 0:
                    if upper[i:i+klen] == keyword and (i == 0 or not sql[i-1].isalnum()):
                        return i
        return -1

    def _block_end_after(pos: int) -> int:
        end = len(sql)
        for kw in (" GROUP BY ", " ORDER BY ", " HAVING ", " UNION ", " INTERSECT ", " MINUS "):
            kw_pos = upper.find(kw, pos)
            if kw_pos >= 0 and kw_pos < end:
                end = kw_pos
        return end

    where_pos = _find_outer_keyword("WHERE ")

    for fc in filters:
        if where_pos >= 0:
            block_end = _block_end_after(where_pos + 6)
            sql = sql[:block_end] + f" AND {fc}" + sql[block_end:]
            where_pos = 0
        else:
            from_pos = _find_outer_keyword("FROM ")
            if from_pos >= 0:
                block_end = _block_end_after(from_pos + 5)
                sql = sql[:block_end] + f" WHERE {fc}" + sql[block_end:]
                where_pos = 0

    return sql


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
        from deepclaw.middleware.nl2sql.ddl.oracle import parse_oracle_url

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
    from deepclaw.middleware.nl2sql.ddl.oracle import (
        init_oracle_thick_client,
        parse_oracle_url,
    )

    _ = parse_oracle_url  # 维持导入引用
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
    def __init__(self, allowed_tables: list[str] | None = None) -> None:
        """初始化 NL2SQL 中间件。

        Args:
            allowed_tables: 可访问表白名单；None 表示使用环境变量或默认全部表。
        """
        super().__init__()
        self._allowed_tables = allowed_tables

    def _get_allowed_tables(self) -> list[str] | None:
        """获取当前中间件生效的可访问表白名单。"""
        return _resolve_allowed_tables(self._allowed_tables)

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

        # 后续可按 user_id 解析授权表列表并与配置白名单合并
        _ = user_id
        allowed_tables = self._get_allowed_tables()
        return fetch_schema_ddl(database_url, table_names=allowed_tables, schema=resolved_schema)

    def get_list_tables_tool(self, user_id: str | None = None, schema: str | None = None):
        """构建列出数据库中所有表的工具。

        Args:
            user_id: 用户标识，当前仅保留扩展位。
            schema: 显式指定的 schema 名称。
        """
        resolved_schema = _resolve_schema(schema)
        allowed_tables = self._get_allowed_tables()

        @tool(description="列出当前数据库中可用的表名（受可访问表白名单限制）")
        def list_tables_tool() -> str:
            """列出数据库中可用的表名"""
            database_url = _resolve_database_url()
            if not database_url:
                return "未配置数据库连接（NL2SQL_DATABASE_URL / PG_DATABASE_URL）"
            try:
                tables = list_tables(database_url, schema=resolved_schema)
                tables = _filter_allowed_tables(tables, allowed_tables)
                if not tables:
                    return "数据库中未找到可访问的数据表"
                return "数据库中的表:\n" + "\n".join(f"- {t}" for t in tables)
            except Exception as exc:
                return f"获取表列表失败：{exc}"

        return list_tables_tool

    def get_describe_tables_tool(self, user_id: str | None = None, schema: str | None = None) -> BaseTool:
        """构建查看指定表 DDL 的工具，复用 fetch_schema_ddl 逻辑。

        Args:
            user_id: 用户标识，当前仅保留扩展位。
            schema: 显式指定的 schema 名称。
        """
        resolved_schema = _resolve_schema(schema)
        allowed_tables = self._get_allowed_tables()

        @tool
        def describe_tables_tool(
            table_names: str = Field(
                description="表名，多个表用逗号分隔，支持 schema.table_name 格式指定模式,未指定 schema 时使用默认的schema"
            ),
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

            denied = _reject_disallowed_tables(raw_names, allowed_tables)
            if denied:
                denied_text = ", ".join(denied)
                allowed_text = ", ".join(allowed_tables or [])
                return f"无权查看表: {denied_text}；可访问表: {allowed_text}"

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
                    if DESCRIBE_TABLES_INLINE_COLUMN_COMMENTS:
                        part = _inline_column_comments(part)
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
        allowed_tables = self._get_allowed_tables()
        # user_ddl = self.get_user_ddl(user_id, schema=resolved_schema)
        # TODO: 过滤条件后续通过外部传入，当前先硬编码
        _sql_filters = []
        # _sql_filters = [
        #     "GRID_ID IN (SELECT DEPT_ID FROM TB_SK_SYS_DEPT WHERE DEPT_ID = '用户部门编码' OR ANCESTORS LIKE '%' || '用户部门编码' || '%')",
        # ]

        @tool
        def run_sql(sql: str = Field(description="SQL 语句")) -> str:
            """用于运行sql语句，你使用的数据库类型是 Oracle。
            # 必须遵守的要求：
            - 仅允许执行查询（SELECT）语句，拒绝写入/修改操作。
            - 禁止在 SQL 中添加任何注释（包括 -- 和 /* */ 注释），请直接输出可执行 SQL。
            - 在查询某个数据库表之前，如果不知道该表的 DDL 结构，必须先使用 describe_tables_tool 查看该表的 DDL 结构，禁止直接去查询表进行DDL结构探索。
            - 查询结果最多展示 30 行；系统会在 SQL 层强制限制返回行数，超出部分会提示数据量过大，建议用 SQL运算或 聚合等操作，或者使用eval工具编写代码来完成任务。
            - 尽量使用简单的 SQL 语句 + 多次查询，避免使用复杂的查询逻辑（因为模型能力有限，复杂SQL命令容易出错）。
            """
            database_url = _resolve_database_url()
            if not database_url:
                return "错误：未配置数据库连接"

            try:
                original_sql = sql
                _validate_readonly(sql)
                _validate_sql_tables_allowed(sql, allowed_tables)
                if _sql_filters:
                    sql = _inject_filters(sql, _sql_filters)

                fetch_limit = MAX_DISPLAY_ROWS + 1
                scheme = _get_database_scheme(database_url)
                sql = _apply_row_limit(sql, fetch_limit, scheme)
                logger.info(f"run_sql 原始 SQL：{original_sql}")
                logger.info(f"run_sql 最终 SQL：{sql}")

                with _make_connection(database_url) as conn:
                    _apply_schema_to_connection(conn, database_url, resolved_schema)
                    with conn.cursor() as cur:
                        cur.execute(sql)

                        # 判断是否有返回结果（SELECT 查询）
                        if cur.description:
                            columns = [desc[0] for desc in cur.description]
                            rows = cur.fetchmany(fetch_limit)

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
            args = request.tool_call["args"]
            if isinstance(args, dict) and "code" in args and "sql" not in args:
                args["sql"] = args.pop("code")
            result = await run_sql_tool.arun(args)
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


async def main():
    middleware = NL2SQLMiddleware()
    describe_tables_tool = middleware.get_describe_tables_tool()
    result = await describe_tables_tool.ainvoke({"table_names": "TB_DW_GRP_SK_NEXT_BUILD_DAY"})
    print(result)


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
