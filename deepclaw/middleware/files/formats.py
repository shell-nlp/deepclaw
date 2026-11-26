"""文件格式解析和生成，供文件服务在线程中调用。"""

import re
from datetime import date, datetime, time, timedelta
from io import BytesIO
from threading import Lock
from zipfile import ZipFile

from docx import Document
from openpyxl import Workbook, load_workbook
from openpyxl.utils import get_column_letter

MAX_ROWS = 100_000
MAX_CELLS = 300_000
MAX_COLUMNS = 256
MAX_UNPACKED = 80 * 1024 * 1024
MAX_TEXT = 8_000_000
PDF_LOCK = Lock()
PDF_IMAGE_MAX_EDGE = 2200


def render_pdf_images(data: bytes, pages: list[int]) -> list[bytes]:
    """将指定 PDF 页渲染为尺寸受限的 JPEG。

    Args:
        data: PDF 原件。
        pages: 从 1 开始的页码。
    """
    import pymupdf

    with PDF_LOCK, pymupdf.open(stream=data, filetype="pdf") as document:
        if document.needs_pass or any(number < 1 or number > len(document) for number in pages):
            raise ValueError("PDF 已加密或页码超出范围。")
        images = []
        for number in pages:
            page = document[number - 1]
            edge = max(page.rect.width, page.rect.height)
            if edge <= 0:
                raise ValueError("PDF 页面尺寸无效。")
            scale = min(2.8, PDF_IMAGE_MAX_EDGE / edge)
            pixmap = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False)
            images.append(pixmap.tobytes("jpeg", jpg_quality=85))
        return images


def _check_archive(data: bytes) -> None:
    """限制 Office 文件展开体积。

    Args:
        data: 文件字节。
    """
    with ZipFile(BytesIO(data)) as archive:
        entries = archive.infolist()
        if len(entries) > 4096 or sum(entry.file_size for entry in entries) > MAX_UNPACKED:
            raise ValueError("Office 文件展开后过大。")


def extract_document(extension: str, data: bytes) -> dict:
    """提取可分行读取的文档正文或工作簿。

    Args:
        extension: 文件后缀。
        data: 原文件字节。
    """
    if extension == ".xlsx":
        return _extract_workbook(data)
    if extension == ".pdf":
        return _extract_pdf(data)
    if extension == ".docx":
        _check_archive(data)
        blocks = []
        for block in Document(BytesIO(data)).iter_inner_content():
            if hasattr(block, "text"):
                blocks.append(block.text)
            else:
                blocks.extend("\t".join(cell.text.replace("\n", " ") for cell in row.cells) for row in block.rows)
        return {"lines": _split_lines("\n".join(blocks))}
    try:
        content = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        content = data.decode("gb18030")
    if "\x00" in content:
        raise ValueError("文件包含非文本数据。")
    return {"lines": _split_lines(content)}


def _split_lines(content: str) -> list[str]:
    """按真实换行拆分文本并保留空行。

    Args:
        content: 文本内容。
    """
    if len(content) > MAX_TEXT:
        raise ValueError("文档正文过长。")
    normalized = content.replace("\r\n", "\n").replace("\r", "\n")
    if not normalized:
        return []
    lines = normalized.removesuffix("\n").split("\n")
    if len(lines) > MAX_ROWS:
        raise ValueError("文档超过 100000 行。")
    return lines


def _extract_pdf(data: bytes) -> dict:
    """串行提取 PDF 文本层，记录页码和无文字页。

    Args:
        data: PDF 文件字节。
    """
    import pymupdf

    lines, pages, empty_pages = [], [], []
    text_size = 0
    with PDF_LOCK, pymupdf.open(stream=data, filetype="pdf") as document:
        if document.needs_pass:
            raise ValueError("请上传已解密的 PDF。")
        if document.page_count > 2000:
            raise ValueError("PDF 超过 2000 页。")
        for number, page in enumerate(document, 1):
            body = page.get_text(sort=True)
            if not body.strip():
                empty_pages.append(number)
                continue
            page_lines = _split_lines(body)
            text_size += len(body)
            if text_size > MAX_TEXT or len(lines) + len(page_lines) > MAX_ROWS:
                raise ValueError("PDF 文本超出解析上限。")
            lines.extend(page_lines)
            pages.extend([number] * len(page_lines))
        return {"lines": lines, "pages": pages, "page_count": document.page_count, "pages_without_text": empty_pages}


def _extract_workbook(data: bytes) -> dict:
    """提取各工作表的原始行与单元格坐标。

    Args:
        data: XLSX 文件字节。
    """
    _check_archive(data)
    cached = load_workbook(BytesIO(data), read_only=True, data_only=True, keep_links=False)
    try:
        formulas = load_workbook(BytesIO(data), read_only=True, data_only=False, keep_links=False)
        try:
            if len(formulas.worksheets) > 50:
                raise ValueError("工作簿最多支持 50 张工作表。")
            sheets = {}
            cell_count = text_size = 0
            for worksheet in formulas.worksheets:
                rows = {}
                number = 0
                values_sheet = cached[worksheet.title]
                worksheet.reset_dimensions()
                values_sheet.reset_dimensions()
                raw_rows = worksheet.iter_rows(max_row=MAX_ROWS + 1)
                cached_rows = values_sheet.iter_rows(max_row=MAX_ROWS + 1)
                for number, (cells, values) in enumerate(zip(raw_rows, cached_rows, strict=True), 1):
                    if number > MAX_ROWS or len(cells) > MAX_COLUMNS:
                        raise ValueError("单个工作表最多支持 100000 行和 256 列。")
                    row = {}
                    for column, (cell, cached_cell) in enumerate(zip(cells, values, strict=True), 1):
                        value = cached_cell.value
                        if value is None and cell.data_type != "f":
                            continue
                        if isinstance(value, (datetime, date, time)):
                            value = value.isoformat()
                        elif isinstance(value, timedelta):
                            value = str(value)
                        entry = {"value": value}
                        if cell.data_type == "f":
                            entry["formula"] = cell.value if isinstance(cell.value, str) else getattr(cell.value, "text", None)
                        column_label = get_column_letter(column)
                        text_size += len(str(entry))
                        cell_count += 1
                        if text_size > MAX_TEXT or cell_count > MAX_CELLS:
                            raise ValueError("Excel 数据超出解析上限。")
                        row[column_label] = entry
                    if row:
                        rows[str(number)] = row
                sheets[worksheet.title] = {"rows": rows, "total_lines": number}
            return {"sheets": sheets}
        finally:
            formulas.close()
    finally:
        cached.close()


def generate_xlsx(sheets: list[dict]) -> bytes:
    """按输入顺序生成多工作表工作簿。

    Args:
        sheets: 工作表名称及行数据。
    """
    if not 1 <= len(sheets) <= 50:
        raise ValueError("请提供 1 至 50 张工作表。")
    workbook = Workbook()
    workbook.remove(workbook.active)
    names = set()
    count = 0
    for sheet in sheets:
        name, rows = sheet["name"], sheet["rows"]
        if not name.strip() or len(name) > 31 or re.search(r"[\[\]:*?/\\]", name) or name.casefold() in names:
            raise ValueError("工作表名称需合法、唯一且不超过 31 个字符。")
        names.add(name.casefold())
        worksheet = workbook.create_sheet(name)
        if len(rows) > MAX_ROWS:
            raise ValueError("单个工作表最多支持 100000 行。")
        for number, row in enumerate(rows, 1):
            count += len(row)
            if len(row) > MAX_COLUMNS or count > MAX_CELLS:
                raise ValueError("工作簿超出列数或单元格上限。")
            for column, value in enumerate(row, 1):
                if isinstance(value, dict):
                    value = date.fromisoformat(value["date"])
                if value is None:
                    continue
                if isinstance(value, str) and len(value) > 32767:
                    raise ValueError("单元格文本超过 32767 字符。")
                cell = worksheet.cell(number, column, value)
                if isinstance(value, str):
                    cell.data_type = "s"
            if not row or all(value is None for value in row):
                worksheet.cell(number, 1)
    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


def generate_docx(markdown: str) -> bytes:
    """将 Markdown 的基础结构导出为 Word。

    Args:
        markdown: 原始 Markdown 正文。
    """
    document = Document()
    lines = _split_lines(markdown)
    index = 0
    while index < len(lines):
        line = lines[index]
        index += 1
        heading = re.match(r"^(#{1,6})\s+(.+)$", line)
        if heading:
            document.add_heading(heading[2], level=len(heading[1]))
        elif "|" in line and index < len(lines) and re.fullmatch(r"[\s|:-]+", lines[index]) and "-" in lines[index]:
            header = [part.strip() for part in line.strip().strip("|").split("|")]
            table = document.add_table(rows=1, cols=len(header))
            table.style = "Table Grid"
            for cell, value in zip(table.rows[0].cells, header):
                cell.text = value
            index += 1
            while index < len(lines) and "|" in lines[index]:
                values = lines[index].strip().strip("|").split("|")
                for cell, value in zip(table.add_row().cells, values):
                    cell.text = value.strip()
                index += 1
        elif match := re.match(r"^\s*([-+*]|\d+\.)\s+(.+)$", line):
            document.add_paragraph(match[2], style="List Bullet" if len(match[1]) == 1 else "List Number")
        else:
            document.add_paragraph(line)
    output = BytesIO()
    document.save(output)
    return output.getvalue()

