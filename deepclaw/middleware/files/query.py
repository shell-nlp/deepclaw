"""文件行读取与搜索。"""

import time

import regex

MAX_LINE_OUTPUT = 3000
MAX_OUTPUT = 16_000
SEARCH_BATCH = 5000
PREVIEW_ROWS = 3
PREVIEW_COLUMNS = 16
PREVIEW_CELL_CHARS = 120
SEARCH_ROW_BUDGET = 2000


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


def build_file_summary(document: dict) -> dict:
    """构建文档结构及每张工作表的限量预览。

    Args:
        document: 解析后的文档。
    """
    summary = inspect_document(document)
    for sheet in summary.get("sheets", []):
        source = document["sheets"][sheet["name"]]
        preview = []
        for number in range(1, min(PREVIEW_ROWS, sheet["total_lines"]) + 1):
            values = source["rows"].get(str(number), {})
            cells = {}
            truncated = len(values) > PREVIEW_COLUMNS
            for column, cell in list(values.items())[:PREVIEW_COLUMNS]:
                value = cell["value"] if cell["value"] is not None else cell.get("formula")
                if isinstance(value, str) and len(value) > PREVIEW_CELL_CHARS:
                    value = value[:PREVIEW_CELL_CHARS]
                    truncated = True
                cells[column] = value
            preview.append({"line": number, "cells": cells, "truncated": truncated})
        sheet["preview"] = preview
    return summary


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


def read_lines(
    document: dict, sheet: str | None, start_line: int, limit: int,
    columns: list[str] | None, *, output_budget: int = MAX_OUTPUT,
) -> dict:
    """读取带稳定行号的有限正文或工作表行。

    Args:
        document: 解析后的文档。
        sheet: 工作表名称，默认第一张。
        start_line: 起始行号，从 1 开始。
        limit: 最多返回的行数。
        columns: Excel 列标列表，例如 A、D。
        output_budget: 返回行内容的字符预算。
    """
    name, source = _select_sheet(document, sheet)
    if columns is not None and name is None:
        raise ValueError("只有 Excel 文件可以指定列。")
    selected = {column.upper() for column in columns} if columns is not None else None
    total = source["total_lines"] if name is not None else len(source["lines"])
    items = []
    budget = output_budget
    for number in range(start_line, min(total + 1, start_line + limit)):
        item = {"line": number}
        if name is None:
            content = source["lines"][number - 1]
            item.update(content=content[:MAX_LINE_OUTPUT], truncated=len(content) > MAX_LINE_OUTPUT)
            if "pages" in source:
                item["page"] = source["pages"][number - 1]
        else:
            cells = source["rows"].get(str(number), {})
            if selected is not None:
                cells = {column: cell for column, cell in cells.items() if column in selected}
            item.update(_render_cells(cells, output_budget - len(str(item))))
        size = len(str(item))
        if items and size > budget:
            break
        budget -= size
        items.append(item)
    next_line = start_line + len(items)
    return {"sheet": name, "lines": items, "total_lines": total,
            "next_start_line": next_line if next_line <= total else None, "eof": next_line > total}


def _render_cells(cells: dict, output_budget: int) -> dict:
    """优先保留短字段，并按各单元格可用的空间截断长文本。

    Args:
        cells: 按工作表顺序排列的列标及单元格。
        output_budget: 当前行可用于单元格和截断标记的字符预算。
    """
    capped = {
        column: {
            key: value[:MAX_LINE_OUTPUT] if isinstance(value, str) else value
            for key, value in cell.items()
        }
        for column, cell in cells.items()
    }
    truncated = [column for column in cells if capped[column] != cells[column]]
    result = {"cells": capped}
    if truncated:
        result.update(truncated=True, truncated_columns=truncated)
    if len(str(result)) <= output_budget:
        return result

    rendered = {}
    # 预留截断列标的空间，避免宽表的列标本身挤出行预算。
    remaining = output_budget - len(str({"cells": {}, "truncated": True, "truncated_columns": list(cells)}))
    ordered = sorted(capped, key=lambda column: len(str(capped[column])))
    for index, column in enumerate(ordered):
        cell = capped[column]
        overhead = len(repr(column)) + 4  # 列标、冒号和分隔符
        allowance = (remaining - overhead * (len(ordered) - index)) // (len(ordered) - index)
        if len(str(cell)) > allowance:
            minimal = {key: "" if isinstance(value, str) else value for key, value in cell.items()}
            if len(str(minimal)) + overhead > remaining:
                continue
            low, high = 0, MAX_LINE_OUTPUT
            # 按实际表示长度计算，引号、换行等转义字符也计入预算。
            while low < high:
                length = (low + high + 1) // 2
                candidate = {
                    key: value[:length] if isinstance(value, str) else value
                    for key, value in cell.items()
                }
                if len(str(candidate)) <= allowance:
                    low = length
                else:
                    high = length - 1
            cell = {key: value[:low] if isinstance(value, str) else value for key, value in cell.items()}
        rendered[column] = cell
        remaining -= len(str(cell)) + overhead

    return {
        "cells": {column: rendered[column] for column in cells if column in rendered},
        "truncated": True,
        "truncated_columns": [column for column in cells if rendered.get(column) != cells[column]],
    }


def search_lines(
    document: dict, pattern: str, use_regex: bool, ignore_case: bool,
    sheet: str | None, limit: int, cursor: int,
    *, exact: bool = False, match_column: str | None = None,
    return_columns: list[str] | None = None,
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
        exact: 字面搜索时匹配完整行或完整单元格。
        match_column: 可选 Excel 搜索列标。
        return_columns: 命中后附带的 Excel 列标。
    """
    if exact and use_regex:
        raise ValueError("精确匹配和正则搜索不能同时使用。")
    if (match_column is not None or return_columns is not None) and "sheets" not in document:
        raise ValueError("只有 Excel 文件可以指定列。")
    match_column = match_column.upper() if match_column is not None else None
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
    exact_column = exact and match_column is not None
    deadline = time.monotonic() + 1.0
    index = 0
    for name, source in sources:
        for number, column, value in _search_rows(name, source, match_column):
            if index < cursor:
                index += 1
                continue
            if len(hits) >= limit or (not exact_column and (
                index - cursor >= SEARCH_BATCH or time.monotonic() >= deadline
            )):
                return {"matches": hits, "next_cursor": index, "search_complete": False}
            try:
                if exact_column:
                    # 固定字面量没有正则回溯，直接扫描有限的 Excel 解析缓存。
                    match = matcher.fullmatch(value)
                elif exact:
                    match = matcher.fullmatch(value, timeout=0.05)
                else:
                    match = matcher.search(value, timeout=0.05)
            except TimeoutError as exc:
                raise ValueError("正则搜索耗时过长，请缩小搜索范围或简化表达式。") from exc
            if match is not None:
                start = max(0, match.start() - 200)
                hit = {"line": number, "content": value[start:start + 600]}
                if name is not None:
                    hit.update(sheet=name, cell=f"{name}!{column}{number}")
                    if return_columns:
                        row = read_lines(document, name, number, 1, return_columns, output_budget=SEARCH_ROW_BUDGET)["lines"][0]
                        hit["cells"] = row["cells"]
                        if row.get("truncated"):
                            hit["truncated"] = True
                            hit["truncated_columns"] = row["truncated_columns"]
                elif "pages" in source:
                    hit["page"] = source["pages"][number - 1]
                size = len(str(hit))
                if hits and size > budget:
                    return {"matches": hits, "next_cursor": index, "search_complete": False}
                budget -= size
                hits.append(hit)
            index += 1
    return {"matches": hits, "next_cursor": None, "search_complete": True}


def _search_rows(name: str | None, source: dict, match_column: str | None = None):
    """按原文或原始单元格顺序提供搜索项。

    Args:
        name: 工作表名称。
        source: 正文或工作表数据。
        match_column: 可选的 Excel 搜索列标。
    """
    if name is None:
        for number, value in enumerate(source["lines"], 1):
            yield number, None, value
    else:
        for number, cells in source["rows"].items():
            if match_column is not None:
                cell = cells.get(match_column)
                if cell is not None:
                    value = cell["value"] if cell["value"] is not None else cell.get("formula", "")
                    yield int(number), match_column, str(value)
                continue
            for column, cell in cells.items():
                value = cell["value"]
                if value is None:
                    value = cell.get("formula", "")
                yield int(number), column, str(value)
