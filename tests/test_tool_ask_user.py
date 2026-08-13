import importlib

import pytest

from deepclaw.tools import ask_user

ask_user_module = importlib.import_module("deepclaw.tools.ask_user")


def test_ask_user_passes_normalized_payload_and_returns_answer(monkeypatch):
    captured = {}

    def fake_interrupt(payload):
        captured["payload"] = payload
        return "用户选择 A"

    monkeypatch.setattr(ask_user_module, "interrupt", fake_interrupt)

    result = ask_user.invoke(
        {
            "question": "  请选择方案？ ",
            "header": "  选择方案 ",
            "options": [
                {"label": " A ", "description": "  立刻发布 "},
                {"label": "B"},
            ],
            "multiple": True,
            "custom": False,
        }
    )

    assert result == "用户选择 A"
    assert captured["payload"] == {
        "question": "请选择方案？",
        "header": "选择方案",
        "options": [
            {"label": "A", "description": "立刻发布"},
            {"label": "B"},
        ],
        "multiple": True,
        "custom": False,
    }


def test_ask_user_omits_empty_optional_values(monkeypatch):
    monkeypatch.setattr(ask_user_module, "interrupt", lambda payload: payload)

    result = ask_user.invoke({"question": "是否继续？", "options": [], "multiple": False})

    assert result == {"question": "是否继续？", "custom": True}


def test_ask_user_rejects_invalid_inputs():
    for arguments in (
        {"question": "   "},
        {"question": "问题", "options": [{"label": "可以"}, {"label": "  "}]},
        {"question": "问题", "header": "x" * 31},
    ):
        with pytest.raises(ValueError):
            ask_user.invoke(arguments)
