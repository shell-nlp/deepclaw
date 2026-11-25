"""向 Agent 提供账号文件工具。"""

import asyncio
import json
from typing import Annotated, Literal

from langchain.agents.middleware import AgentMiddleware
from langchain.tools import ToolRuntime, tool
from pydantic import BaseModel, Field

from deepclaw.middleware.files.formats import generate_docx, generate_xlsx
from deepclaw.middleware.files.query import inspect_document, read_lines, search_lines
from deepclaw.middleware.files.service import file_details, get_file_service
from deepclaw.web_backend.auth.rbac.dependencies import agent_has_permission


class DateCellRequest(BaseModel):
    """ISO 日期单元格。"""

    date: str


class SheetRequest(BaseModel):
    """工作表及按原列顺序提交的行。"""

    name: str
    rows: list[list[str | int | float | bool | DateCellRequest | None]]


async def _owner(runtime: ToolRuntime, *actions: str) -> str:
    """校验工具调用的用户和文件权限。

    Args:
        runtime: 框架注入的运行时。
        actions: 所需权限动作。
    """
    principal = runtime.config.get("configurable", {}).get("langgraph_auth_user")
    owner = getattr(principal, "identity", None)
    if not owner or owner == "guest":
        raise ValueError("请登录后使用聊天文件。")
    for action in actions:
        if not await agent_has_permission(owner, "/api/files", action):
            raise ValueError("当前账号缺少相应的聊天文件权限。")
    return owner


@tool
async def list_files(
    runtime: ToolRuntime,
    offset: Annotated[int, Field(ge=0)] = 0,
    limit: Annotated[int, Field(ge=1, le=50)] = 20,
) -> str:
    """列出当前账号上传或生成的聊天文件。

    Args:
        runtime: 框架注入的运行时。
        offset: 跳过的记录数量。
        limit: 每页最多返回的文件数。
    """
    try:
        owner = await _owner(runtime, "read")
        files = await get_file_service().list(owner, offset, limit + 1)
        return json.dumps({
            "files": [file_details(record) for record in files[:limit]],
            "next_offset": offset + limit if len(files) > limit else None,
        }, ensure_ascii=False)
    except ValueError as exc:
        return str(exc)


@tool
async def inspect_file(runtime: ToolRuntime, file_id: str) -> str:
    """查看聊天文件的行数、Excel Sheet 名称或 PDF 页码范围。

    Args:
        runtime: 框架注入的运行时。
        file_id: 聊天附件或 list_files 返回的文件 ID。
    """
    try:
        owner = await _owner(runtime, "read")
        service = get_file_service()
        record = await service.get(owner, file_id)
        document = await service.parsed(record)
        return json.dumps({**file_details(record), **inspect_document(document)}, ensure_ascii=False)
    except (LookupError, ValueError) as exc:
        return str(exc)


@tool
async def read_file(
    runtime: ToolRuntime,
    file_id: str,
    start_line: Annotated[int, Field(ge=1)] = 1,
    limit: Annotated[int, Field(ge=1, le=200)] = 100,
    sheet: str | None = None,
    columns: Annotated[list[Annotated[str, Field(pattern=r"^[A-Za-z]{1,3}$")]], Field(max_length=256)] | None = None,
) -> str:
    """分页读取聊天文件。用 next_start_line 继续，并以返回行号引用原文。

    Args:
        runtime: 框架注入的运行时。
        file_id: 聊天附件或 list_files 返回的文件 ID。
        start_line: 起始行号，从 1 开始。
        limit: 本次最多返回的行数。
        sheet: Excel 工作表名称，省略时读取第一张。
        columns: 可选 Excel 列标列表，例如 ["A", "D"]。
    """
    try:
        owner = await _owner(runtime, "read")
        service = get_file_service()
        record = await service.get(owner, file_id)
        document = await service.parsed(record)
        result = await asyncio.to_thread(read_lines, document, sheet, start_line, limit, columns)
        return json.dumps(result, ensure_ascii=False)
    except (LookupError, ValueError) as exc:
        return str(exc)


@tool
async def grep_file(
    runtime: ToolRuntime,
    file_id: str,
    pattern: Annotated[str, Field(min_length=1, max_length=500)],
    use_regex: bool = False,
    ignore_case: bool = False,
    sheet: str | None = None,
    limit: Annotated[int, Field(ge=1, le=100)] = 30,
    cursor: Annotated[int, Field(ge=0)] = 0,
) -> str:
    """搜索聊天文件。命中包含原文行号、PDF 页码或 Excel 单元格坐标。

    Args:
        runtime: 框架注入的运行时。
        file_id: 聊天附件或 list_files 返回的文件 ID。
        pattern: 文本或正则表达式。
        use_regex: 启用正则，默认按字面搜索。
        ignore_case: 是否忽略大小写。
        sheet: Excel 工作表名称，省略时搜索整本。
        limit: 最大命中数量。
        cursor: 使用相同查询条件时传入上一页的 next_cursor。
    """
    try:
        owner = await _owner(runtime, "read")
        service = get_file_service()
        record = await service.get(owner, file_id)
        document = await service.parsed(record)
        result = await asyncio.to_thread(search_lines, document, pattern, use_regex, ignore_case, sheet, limit, cursor)
        return json.dumps(result, ensure_ascii=False)
    except (LookupError, ValueError) as exc:
        return str(exc)


@tool
async def write_file(
    runtime: ToolRuntime,
    name: str,
    format: Literal["md", "xlsx"] = "md",
    content: str | None = None,
    sheets: list[SheetRequest] | None = None,
) -> str:
    """生成供用户下载的 Markdown 或多 Sheet Excel。回复中使用返回的 download_url 作为 Markdown 下载链接。

    Args:
        runtime: 框架注入的运行时。
        name: 生成的文件名，可省略后缀。
        format: Markdown 使用 md，Excel 使用 xlsx。
        content: Markdown 正文，仅在 md 模式使用。
        sheets: Excel 工作表与数据行，日期单元格使用 {"date": "2026-11-25"}。
    """
    try:
        owner = await _owner(runtime, "write")
        if format == "md" and content is not None and sheets is None:
            data = content.encode("utf-8")
        elif format == "xlsx" and sheets is not None and content is None:
            data = await asyncio.to_thread(generate_xlsx, [sheet.model_dump() for sheet in sheets])
        else:
            return "生成 Markdown 请提供 content，生成 Excel 请提供 sheets。"
        suffix = f".{format}"
        filename = name if name.lower().endswith(suffix) else name + suffix
        record = await get_file_service().save(owner, filename, data)
        return json.dumps(file_details(record), ensure_ascii=False)
    except ValueError as exc:
        return str(exc)


@tool
async def export_file(runtime: ToolRuntime, file_id: str, name: str | None = None) -> str:
    """将已有 Markdown 导出为 Word。回复中使用返回的 download_url 作为 Markdown 下载链接。

    Args:
        runtime: 框架注入的运行时。
        file_id: Markdown 文件 ID。
        name: 可选的 Word 文件名。
    """
    try:
        owner = await _owner(runtime, "read", "write")
        service = get_file_service()
        source = await service.get(owner, file_id)
        if source.extension != ".md":
            return "当前支持将 Markdown 导出为 Word。"
        parsed = await service.parsed(source)
        data = await asyncio.to_thread(generate_docx, "\n".join(parsed["lines"]))
        filename = name or source.name[:-3] + ".docx"
        if not filename.lower().endswith(".docx"):
            filename += ".docx"
        record = await service.save(owner, filename, data)
        return json.dumps(file_details(record), ensure_ascii=False)
    except (LookupError, ValueError) as exc:
        return str(exc)


class FileMiddleware(AgentMiddleware):
    """为不同 Agent 装配相同的聊天文件工具。"""

    def __init__(self, *, keep_workspace_tools: bool = False):
        """注册工具并处理 DeepAgent 工作区工具的同名冲突。

        Args:
            keep_workspace_tools: 是否为聊天文件的读写工具加前缀。
        """
        read = read_file
        write = write_file
        if keep_workspace_tools:
            read = read_file.model_copy(update={"name": "read_chat_file"})
            write = write_file.model_copy(update={"name": "write_chat_file"})
        self.tools = [list_files, inspect_file, read, grep_file, write, export_file]
