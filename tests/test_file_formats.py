import asyncio
from base64 import b64decode
from types import SimpleNamespace

import pymupdf
import pytest

from deepclaw.middleware.files.formats import extract_document, generate_xlsx
from deepclaw.middleware.files.query import inspect_document, read_lines, search_lines


@pytest.mark.parametrize("keep_workspace_tools, pages", [(False, None), (True, [1])])
def test_pdf_read_reaches_model_as_an_image(monkeypatch, keep_workspace_tools, pages):
    """验证只有图片的 PDF 通过工具进入模型请求，图状态只保留页码。

    Args:
        monkeypatch: 替换文件服务与读取权限。
        keep_workspace_tools: 保留 DeepAgent 工作区工具时使用聊天文件别名。
        pages: 显式选页，或自动选取无文字页。
    """
    from langchain.agents import create_agent
    from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
    from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

    from deepclaw.middleware.files import middleware
    from deepclaw.utils.model_factory import ReasoningChatOpenAI

    with pymupdf.open() as pdf:
        pdf.new_page().insert_text((45, 60), "4862")
        raster = pdf[0].get_pixmap().tobytes()
    with pymupdf.open() as pdf:
        pdf.new_page().insert_image(pdf[0].rect, stream=raster)
        original = pdf.tobytes()
    document = extract_document(".pdf", original)
    assert document["pages_without_text"] == [1]
    record = SimpleNamespace(name="report.pdf", extension=".pdf")

    async def get(owner, file_id):
        """替换原件归属校验。

        Args:
            owner: 当前账号。
            file_id: 目标文件。
        """
        assert (owner, file_id) == ("alice", "report")
        return record

    async def parsed(record):
        """读取已解析的页面数据。

        Args:
            record: 通过归属校验的记录。
        """
        return document

    async def download(record):
        """读取测试构造的原件。

        Args:
            record: 通过归属校验的记录。
        """
        return original

    async def permission(owner, path, action):
        """允许测试用户读取文件。

        Args:
            owner: 当前账号。
            path: 权限路径。
            action: 权限动作。
        """
        return (owner, path, action) == ("alice", "/api/files", "read")

    service = SimpleNamespace(get=get, parsed=parsed, download=download)
    monkeypatch.setattr(middleware, "get_file_service", lambda: service)
    monkeypatch.setattr(middleware, "agent_has_permission", permission)
    observed = []

    class Model(FakeMessagesListChatModel):
        """记录实际进入模型的消息。"""

        def bind_tools(self, tools, **kwargs):
            """保留测试模型作为工具绑定结果。

            Args:
                tools: 智能体工具。
                kwargs: 模型绑定参数。
            """
            return self

        def _generate(self, messages, *args, **kwargs):
            """记录模型输入并生成预设回复。

            Args:
                messages: 送入模型的消息。
                args: 模型生成参数。
                kwargs: 模型生成选项。
            """
            observed.append(messages)
            return super()._generate(messages, *args, **kwargs)

    read_name = "read_chat_file" if keep_workspace_tools else "read_file"
    arguments = {"file_id": "report"}
    if pages is not None:
        arguments["pages"] = pages
    model = Model(responses=[
        AIMessage(content="", tool_calls=[{"name": read_name, "id": "view-1", "args": arguments}]),
        AIMessage(content="done"),
    ])
    agent = create_agent(model, middleware=[middleware.FileMiddleware(keep_workspace_tools=keep_workspace_tools)])
    state = asyncio.run(agent.ainvoke(
        {"messages": [HumanMessage(content="看 PDF")]},
        {"configurable": {"langgraph_auth_user": SimpleNamespace(identity="alice", permissions=[])}},
    ))
    sent = observed[-1][-1]
    assert isinstance(sent, HumanMessage)
    url = sent.content[1]["image_url"]["url"]
    assert b64decode(url.split(",", 1)[1]).startswith(b"\xff\xd8")
    for use_responses_api in (False, True):
        transport = ReasoningChatOpenAI(model="test", api_key="test", use_responses_api=use_responses_api)
        payload = transport._get_request_payload(observed[-1])
        assert url in str(payload)
    tool_result = next(message for message in state["messages"] if isinstance(message, ToolMessage))
    assert tool_result.artifact["pages"] == [1]
    assert url not in str(state["messages"])


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
