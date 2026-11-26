"""向 Agent 提供账号文件工具。"""

import asyncio
import json
from base64 import b64encode
from typing import Annotated, Literal

from langchain.agents.middleware import AgentMiddleware
from langchain.tools import ToolRuntime, tool
from langchain_core.messages import HumanMessage, ToolMessage
from langgraph.config import get_config
from pydantic import BaseModel, Field

from deepclaw.middleware.files.formats import generate_docx, generate_xlsx, render_pdf_images
from deepclaw.middleware.files.query import read_lines, search_lines
from deepclaw.middleware.files.service import file_details, get_file_service
from deepclaw.web_backend.auth.rbac.dependencies import agent_has_permission

PDF_IMAGE_BATCH = 2


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
    keyword: Annotated[str, Field(max_length=255)] | None = None,
    format: Literal["txt", "md", "pdf", "docx", "xlsx"] | None = None,
    favorite: bool | None = None,
) -> str:
    """列出当前账号上传或生成的聊天文件。

    Args:
        runtime: 框架注入的运行时。
        offset: 跳过的记录数量。
        limit: 每页最多返回的文件数。
        keyword: 文件名关键词，按字面匹配，忽略大小写。
        format: 限定文件格式。
        favorite: 为真时只列收藏，为假时只列未收藏，省略时列两者。
    """
    try:
        owner = await _owner(runtime, "read")
        files = await get_file_service().list(
            owner, offset, limit + 1, favorite,
            keyword=keyword, extension=f".{format}" if format is not None else None,
        )
        return json.dumps({
            "files": [file_details(record) for record in files[:limit]],
            "next_offset": offset + limit if len(files) > limit else None,
        }, ensure_ascii=False)
    except ValueError as exc:
        return str(exc)


@tool
async def inspect_file(runtime: ToolRuntime, file_id: str, sheet: str | None = None) -> str:
    """查看文档结构，指定 Excel Sheet 时预览最多三行原始数据。

    PDF 的 pages_without_text 表示无法直接提取文字的页，可用聊天文件读取工具按页查看。

    Args:
        runtime: 框架注入的运行时。
        file_id: 聊天附件或 list_files 返回的文件 ID。
        sheet: 可选的 Excel 工作表名称。预览保留列标与行号，不推断表头。
    """
    try:
        owner = await _owner(runtime, "read")
        service = get_file_service()
        record = await service.get(owner, file_id)
        summary = await service.summary(record)
        if "sheets" in summary:
            sheets = summary["sheets"]
            summary["sheets"] = [{"name": entry["name"], "total_lines": entry["total_lines"]} for entry in sheets]
            if sheet is not None:
                selected = next((entry for entry in sheets if entry["name"] == sheet), None)
                if selected is None:
                    return "找不到指定的 Sheet。"
                summary.update(sheet=sheet, preview=selected["preview"])
        elif sheet is not None:
            return "只有 Excel 文件可以指定 Sheet。"
        return json.dumps({**file_details(record), **summary}, ensure_ascii=False)
    except (LookupError, ValueError) as exc:
        return str(exc)


@tool(response_format="content_and_artifact")
async def read_file(
    runtime: ToolRuntime,
    file_id: str,
    start_line: Annotated[int, Field(ge=1)] = 1,
    limit: Annotated[int, Field(ge=1, le=200)] = 100,
    sheet: str | None = None,
    columns: Annotated[list[Annotated[str, Field(pattern=r"^[A-Za-z]{1,3}$")]], Field(max_length=256)] | None = None,
    pages: Annotated[list[Annotated[int, Field(ge=1)]], Field(min_length=1, max_length=PDF_IMAGE_BATCH)] | None = None,
) -> tuple[str, dict | None]:
    """分页读取聊天文件。用 next_start_line 继续，并以返回行号引用原文。

    首次读取 PDF 时，自动附带最多两页无法提取文字的页面图片。
    如需查看指定 PDF 页的图表、版面或其余无文字页，使用 pages。

    Args:
        runtime: 框架注入的运行时。
        file_id: 聊天附件或 list_files 返回的文件 ID。
        start_line: 起始行号，从 1 开始。
        limit: 本次最多返回的行数。
        sheet: Excel 工作表名称，省略时读取第一张。
        columns: 可选 Excel 列标列表，例如 ["A", "D"]。
        pages: 按图片查看的 PDF 原始页码，从 1 开始，每次最多两页。
    """
    try:
        owner = await _owner(runtime, "read")
        service = get_file_service()
        record = await service.get(owner, file_id)
        if pages is not None and record.extension != ".pdf":
            raise ValueError("只有 PDF 文件可以指定页码查看图片。")
        if pages is not None and (sheet is not None or columns is not None):
            raise ValueError("按 PDF 页码查看时不能指定 Excel 工作表或列。")
        document = await service.parsed(record)
        missing_text = document.get("pages_without_text", [])
        if pages is not None:
            image_pages = list(dict.fromkeys(pages))
            if any(page > document["page_count"] for page in image_pages):
                raise ValueError(f"页码超出范围。该 PDF 共 {document['page_count']} 页。")
            result = {"page_count": document["page_count"]}
        else:
            result = await asyncio.to_thread(read_lines, document, sheet, start_line, limit, columns)
            image_pages = missing_text[:PDF_IMAGE_BATCH] if start_line == 1 else []
        if missing_text:
            result["pages_without_text"] = missing_text
        artifact = None
        if image_pages:
            result["image_pages"] = image_pages
            artifact = {"owner": owner, "file_id": file_id, "pages": image_pages}
        return json.dumps(result, ensure_ascii=False), artifact
    except (LookupError, ValueError, FileNotFoundError) as exc:
        return str(exc), None


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
    exact: bool = False,
    match_column: Annotated[str, Field(pattern=r"^[A-Za-z]{1,3}$")] | None = None,
    return_columns: Annotated[list[Annotated[str, Field(pattern=r"^[A-Za-z]{1,3}$")]], Field(max_length=256)] | None = None,
) -> str:
    """搜索聊天文件。命中包含原文行号、PDF 页码或 Excel 单元格坐标。

    若 search_complete 为 false，即使本页无命中，也应使用 next_cursor 继续搜索。
    Excel 按指定列精确匹配适合查询订单号等完整标识。
    PDF 的 pages_without_text 未参与搜索，可用聊天文件读取工具按页查看。

    Args:
        runtime: 框架注入的运行时。
        file_id: 聊天附件或 list_files 返回的文件 ID。
        pattern: 文本或正则表达式。
        use_regex: 启用正则，默认按字面搜索。
        ignore_case: 是否忽略大小写。
        sheet: Excel 工作表名称，省略时搜索整本。
        limit: 最大命中数量。
        cursor: 使用相同查询条件时传入上一页的 next_cursor。
        exact: 按完整行或完整单元格匹配，不能和正则同时使用。
        match_column: Excel 搜索列标，例如订单号所在的 A 列。
        return_columns: Excel 命中后附带同一行的指定列，例如金额和状态所在的 D、E 列。
    """
    try:
        owner = await _owner(runtime, "read")
        service = get_file_service()
        record = await service.get(owner, file_id)
        document = await service.parsed(record)
        result = await asyncio.to_thread(
            search_lines, document, pattern, use_regex, ignore_case, sheet, limit, cursor,
            exact=exact, match_column=match_column, return_columns=return_columns,
        )
        if document.get("pages_without_text"):
            result["pages_without_text"] = document["pages_without_text"]
        return json.dumps(result, ensure_ascii=False)
    except (LookupError, ValueError) as exc:
        return str(exc)


@tool
async def write_file(
    runtime: ToolRuntime,
    name: str,
    format: Literal["md", "xlsx", "docx"] = "md",
    content: str | None = None,
    sheets: list[SheetRequest] | None = None,
) -> str:
    """生成供用户下载的 Markdown、多 Sheet Excel 或 Word。回复中使用返回的 download_url 作为 Markdown 下载链接。

    Args:
        runtime: 框架注入的运行时。
        name: 生成的文件名，可省略后缀。
        format: Markdown 使用 md，Excel 使用 xlsx，Word 使用 docx。
        content: Markdown 正文，用于 md 和 docx。
        sheets: Excel 工作表与数据行，日期单元格使用 {"date": "2026-11-25"}。
    """
    try:
        owner = await _owner(runtime, "write")
        if format == "md" and content is not None and sheets is None:
            data = content.encode("utf-8")
        elif format == "docx" and content is not None and sheets is None:
            data = await asyncio.to_thread(generate_docx, content)
        elif format == "xlsx" and sheets is not None and content is None:
            data = await asyncio.to_thread(generate_xlsx, [sheet.model_dump() for sheet in sheets])
        else:
            return "生成 Markdown 或 Word 请只提供 content，生成 Excel 请只提供 sheets。"
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
        self._read_tool_name = read.name
        self.tools = [list_files, inspect_file, read, grep_file, write, export_file]

    async def awrap_model_call(self, request, handler):
        """将最新一批 PDF 工具请求转换为本次模型可见的图像输入。

        Args:
            request: 本次模型调用的消息和模型配置。
            handler: 下一层模型调用处理器。
        """
        pending = []
        for message in reversed(request.messages):
            if not isinstance(message, ToolMessage):
                break
            if message.name == self._read_tool_name and isinstance(message.artifact, dict):
                pending.append(message.artifact)
        if not pending:
            return await handler(request)

        config = get_config().get("configurable", {})
        owner = getattr(config.get("langgraph_auth_user"), "identity", None)
        if not owner or owner == "guest" or not await agent_has_permission(owner, "/api/files", "read"):
            return await handler(request.override(messages=[
                *request.messages, HumanMessage(content="文件读取权限已失效，PDF 页面图片未提供。"),
            ]))
        blocks = []
        remaining = PDF_IMAGE_BATCH
        for artifact in reversed(pending):
            if artifact.get("owner") != owner:
                continue
            if not remaining:
                blocks.append({"type": "text", "text": "本次最多查看两页，请另行请求其余页。"})
                break
            pages = artifact["pages"][:remaining]
            try:
                service = get_file_service()
                record = await service.get(owner, artifact["file_id"])
                data = await service.download(record)
                images = await asyncio.to_thread(render_pdf_images, data, pages)
            except (LookupError, ValueError, OSError, RuntimeError):
                blocks.append({"type": "text", "text": "PDF 页面图片生成失败，请检查原件或换页。"})
                continue
            for number, image in zip(pages, images, strict=True):
                url = "data:image/jpeg;base64," + b64encode(image).decode("ascii")
                blocks.extend([
                    {"type": "text", "text": f"PDF「{record.name}」第 {number} 页。"},
                    {"type": "image_url", "image_url": {"url": url}},
                ])
            remaining -= len(images)
            if len(pages) < len(artifact["pages"]):
                blocks.append({"type": "text", "text": "本次最多查看两页，请另行请求其余页。"})
        if blocks:
            request = request.override(messages=[*request.messages, HumanMessage(content=blocks)])
        return await handler(request)
