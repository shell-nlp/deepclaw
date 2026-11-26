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


def test_workbook_exact_column_search_reaches_late_rows_and_resumes():
    """验证精确查单能够跳过常规搜索分批限制并保留重复命中的分页。"""
    rows = {str(line): {"A": {"value": f"X{line}"}} for line in range(1, 20_001)}
    rows["19999"]["A"]["value"] = "X18732"
    parsed = {"sheets": {"明细": {"total_lines": 20_000, "rows": rows}}}
    options = {"exact": True, "match_column": "a"}

    first = search_lines(parsed, "x18732", False, True, "明细", 1, 0, **options)
    assert [hit["line"] for hit in first["matches"]] == [18_732]
    assert first["search_complete"] is False
    second = search_lines(parsed, "x18732", False, True, "明细", 1, first["next_cursor"], **options)
    assert [hit["line"] for hit in second["matches"]] == [19_999]
    final = search_lines(parsed, "x18732", False, True, "明细", 1, second["next_cursor"], **options)
    assert final == {"matches": [], "next_cursor": None, "search_complete": True}

    missing = search_lines(parsed, "missing", False, False, "明细", 30, 0, **options)
    assert missing == {"matches": [], "next_cursor": None, "search_complete": True}
    partial = search_lines(parsed, "X18732", True, False, "明细", 30, 0)
    assert partial == {"matches": [], "next_cursor": 5000, "search_complete": False}


def test_workbook_long_note_does_not_hide_later_fields():
    """验证长备注被截断时，读取和搜索仍返回后面的金额、状态和列标。"""
    note = ("备注\n" * 1000) + "尾"
    parsed = extract_document(".xlsx", generate_xlsx([{
        "name": "明细",
        "rows": [["X123", note, 17, "已支付"]],
    }]))
    row = read_lines(parsed, "明细", 1, 1, ["B", "C", "D"])["lines"][0]
    hit = search_lines(
        parsed, "X123", False, False, "明细", 1, 0,
        exact=True, match_column="A", return_columns=["B", "C", "D"],
    )["matches"][0]

    for result in (row, hit):
        assert result["truncated"] is True
        assert result["truncated_columns"] == ["B"]
        assert result["cells"]["C"] == {"value": 17}
        assert result["cells"]["D"] == {"value": "已支付"}
        preview = result["cells"]["B"]["value"]
        assert preview and note.startswith(preview) and len(preview) < len(note)
    assert len(str(hit["cells"])) < 2000
