"""文件行读取与搜索。"""

import time

import regex

MAX_LINE_OUTPUT = 3000
MAX_OUTPUT = 16_000
SEARCH_BATCH = 5000


def inspect_document(document: dict) -> dict:
    """提取正文行数或工作表清单。

    Args:
        document: 解析后的文档。
    """
    if "sheets" in document:
        return {"sheets": [
            {"name": name, "total_lines": sheet["total_lines"]}
            for name, sheet in document["sheets"].items()
        ]}
    return {"total_lines": len(document["lines"]), **{
        key: document[key] for key in ("page_count", "pages_without_text") if key in document
    }}


def _select_sheet(document: dict, sheet: str | None) -> tuple[str | None, dict]:
    """选择待阅读的正文或工作表。

    Args:
        document: 解析后的文档。
        sheet: 工作表名称。
    """
    sheets = document.get("sheets")
    if sheets is None:
        if sheet is not None:
            raise ValueError("只有 Excel 文件可以指定 Sheet。")
        return None, document
    name = sheet if sheet is not None else next(iter(sheets))
    if name not in sheets:
        raise ValueError("找不到指定的 Sheet，请先用 inspect_file 查看工作表名称。")
    return name, sheets[name]


def read_lines(document: dict, sheet: str | None, start_line: int, limit: int, columns: list[str] | None) -> dict:
    """读取带稳定行号的有限正文或工作表行。

    Args:
        document: 解析后的文档。
        sheet: 工作表名称，默认第一张。
        start_line: 起始行号，从 1 开始。
        limit: 最多返回的行数。
        columns: Excel 列标列表，例如 A、D。
    """
    name, source = _select_sheet(document, sheet)
    if columns is not None and name is None:
        raise ValueError("只有 Excel 文件可以指定列。")
    selected = {column.upper() for column in columns} if columns is not None else None
    total = source["total_lines"] if name is not None else len(source["lines"])
    items = []
    budget = MAX_OUTPUT
    for number in range(start_line, min(total + 1, start_line + limit)):
        item = {"line": number}
        if name is None:
            content = source["lines"][number - 1]
            item.update(content=content[:MAX_LINE_OUTPUT], truncated=len(content) > MAX_LINE_OUTPUT)
            if "pages" in source:
                item["page"] = source["pages"][number - 1]
        else:
            cells = source["rows"].get(str(number), {})
            item["cells"] = {}
            for column, cell in cells.items():
                if selected is not None and column not in selected:
                    continue
                for key, value in cell.items():
                    if isinstance(value, str) and len(value) > MAX_LINE_OUTPUT:
                        item["truncated"] = True
                        value = value[:MAX_LINE_OUTPUT]
                    item["cells"].setdefault(column, {})[key] = value
                if len(str(item["cells"])) > MAX_OUTPUT - 100:
                    del item["cells"][column]
                    item["truncated"] = True
                    break
        size = len(str(item))
        if items and size > budget:
            break
        budget -= size
        items.append(item)
    next_line = start_line + len(items)
    return {"sheet": name, "lines": items, "total_lines": total,
            "next_start_line": next_line if next_line <= total else None, "eof": next_line > total}


def search_lines(
    document: dict, pattern: str, use_regex: bool, ignore_case: bool,
    sheet: str | None, limit: int, cursor: int,
) -> dict:
    """按正文行或工作簿单元格搜索。

    Args:
        document: 解析后的文档。
        pattern: 字面文本或正则。
        use_regex: 是否按正则解释。
        ignore_case: 是否忽略大小写。
        sheet: 指定工作表，默认查整本。
        limit: 最大命中数。
        cursor: 上一页返回的续搜位置。
    """
    try:
        matcher = regex.compile(pattern if use_regex else regex.escape(pattern), regex.I if ignore_case else 0)
    except regex.error as exc:
        raise ValueError("正则表达式无效。") from exc

    if sheet is None and "sheets" in document:
        sources = document["sheets"].items()
    else:
        sources = [_select_sheet(document, sheet)]
    hits = []
    budget = MAX_OUTPUT
    deadline = time.monotonic() + 1.0
    index = 0
    for name, source in sources:
        for number, column, value in _search_rows(name, source):
            if index < cursor:
                index += 1
                continue
            if index - cursor >= SEARCH_BATCH or len(hits) >= limit or time.monotonic() >= deadline:
                return {"matches": hits, "next_cursor": index}
            try:
                match = matcher.search(value, timeout=0.05)
            except TimeoutError as exc:
                raise ValueError("正则搜索耗时过长，请缩小搜索范围或简化表达式。") from exc
            if match is not None:
                start = max(0, match.start() - 200)
                hit = {"line": number, "content": value[start:start + 600]}
                if name is not None:
                    hit.update(sheet=name, cell=f"{name}!{column}{number}")
                elif "pages" in source:
                    hit["page"] = source["pages"][number - 1]
                size = len(str(hit))
                if hits and size > budget:
                    return {"matches": hits, "next_cursor": index}
                budget -= size
                hits.append(hit)
            index += 1
    return {"matches": hits, "next_cursor": None}


def _search_rows(name: str | None, source: dict):
    """按原文或原始单元格顺序提供搜索项。

    Args:
        name: 工作表名称。
        source: 正文或工作表数据。
    """
    if name is None:
        for number, value in enumerate(source["lines"], 1):
            yield number, None, value
    else:
        for number, cells in source["rows"].items():
            for column, cell in cells.items():
                value = cell["value"]
                if value is None:
                    value = cell.get("formula", "")
                yield int(number), column, str(value)
