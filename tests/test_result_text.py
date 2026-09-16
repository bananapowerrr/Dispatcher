# -*- coding: utf-8 -*-
from ui.result_text import extract_result_text


def test_nested_skill_done():
    data = {
        "id": "t1",
        "status": "DONE",
        "result": {"method": "skill", "skill": "rename_symbol", "stdout": "renamed 2"},
    }
    s = extract_result_text(data)
    assert "rename_symbol" in s
    assert "renamed" in s or "ok" in s or "skill:" in s


def test_nested_error_with_hint():
    data = {
        "result": {
            "worker": "aider_local",
            "error": "verify failed: pytest exit 1",
            "phase": "verify",
        }
    }
    s = extract_result_text(data)
    assert "aider_local" in s
    assert "verify" in s.lower() or "pytest" in s.lower()
    assert "Подсказка" in s


def test_timeout_hint():
    s = extract_result_text({"result": {"error": "timeout after 300s", "worker": "aider_local"}})
    assert "timeout" in s.lower() or "Timeout" in s or "Подсказка" in s


def test_plain_string_result():
    assert extract_result_text({"result": "all good"}) == "all good"
