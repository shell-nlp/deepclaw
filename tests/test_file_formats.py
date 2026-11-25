import pymupdf

from deepclaw.middleware.files.formats import extract_document, generate_xlsx
from deepclaw.middleware.files.query import inspect_document, read_lines, search_lines


def test_workbook_roundtrip_preserves_sheets_rows_and_coordinates():
    """验证多 Sheet 生成和解析共享相同的原始坐标。

    Args:
        无。
    """
    data = generate_xlsx([
        {"name": "汇总", "rows": [[10, None, {"date": "2026-11-25"}], []]},
        {"name": "空表", "rows": []},
        {"name": "明细", "rows": [[], [None, None, None, "目标"], ["=保存为文本"]]},
    ])
    parsed = extract_document(".xlsx", data)
    assert inspect_document(parsed)["sheets"] == [
        {"name": "汇总", "total_lines": 2},
        {"name": "空表", "total_lines": 0},
        {"name": "明细", "total_lines": 3},
    ]
    assert read_lines(parsed, "明细", 1, 2, ["D"])["lines"] == [
        {"line": 1, "cells": {}}, {"line": 2, "cells": {"D": {"value": "目标"}}},
    ]
    assert search_lines(parsed, "^目标$", True, False, None, 30, 0)["matches"] == [
        {"sheet": "明细", "line": 2, "cell": "明细!D2", "content": "目标"},
    ]
    assert read_lines(parsed, "明细", 3, 2, None)["lines"][0]["cells"]["A"] == {"value": "=保存为文本"}


def test_pdf_preserves_page_numbers_across_blank_pages():
    """验证 PDF 连续行号与原页码，并标记无文字页。

    Args:
        无。
    """
    with pymupdf.open() as pdf:
        pdf.new_page().insert_text((40, 40), "Page one")
        pdf.new_page()
        pdf.new_page().insert_text((40, 40), "Page three")
        parsed = extract_document(".pdf", pdf.tobytes())
    assert inspect_document(parsed)["pages_without_text"] == [2]
    assert read_lines(parsed, None, 2, 100, None)["lines"][0]["page"] == 3
    found = search_lines(parsed, "three", False, False, None, 30, 0)["matches"][0]
    assert (found["line"], found["page"]) == (2, 3)
