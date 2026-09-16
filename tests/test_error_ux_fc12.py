# -*- coding: utf-8 -*-
"""FC-12: human-readable errors without traceback spam."""
from __future__ import annotations

from core.error_ux import (
    strip_traceback,
    classify_error,
    humanize_error,
    humanize_from_row,
)


def test_strip_traceback_keeps_exception_line():
    tb = '''Traceback (most recent call last):
  File "runtime.py", line 10, in run
    raise TimeoutError("worker timed out after 300s")
TimeoutError: worker timed out after 300s
'''
    out = strip_traceback(tb)
    assert "TimeoutError" in out
    assert "File \"" not in out


def test_classify_timeout():
    code, hint = classify_error("TimeoutExpired: command exceeded")
    assert code == "timeout"
    assert "timeout" in hint.lower() or "Ollama" in hint


def test_classify_verify():
    code, hint = classify_error("verification_failed: pytest")
    assert code == "verify"
    assert "DONE" in hint or "Верификация" in hint


def test_humanize_includes_hint():
    msg = humanize_error(
        "pytest failed\n1 failed, 0 passed",
        worker="aider_local",
        verification_summary="Verify FAIL (0/1): pytest",
    )
    assert "aider" in msg
    assert "→" in msg
    assert "pytest" in msg.lower() or "Verify" in msg


def test_humanize_from_row_error_json():
    row = {
        "id": "t1",
        "status": "ERROR",
        "result": {
            "ok": False,
            "worker": "ollama",
            "error": "Connection refused: ollama not running",
        },
    }
    msg = humanize_from_row(row)
    assert "ollama" in msg.lower() or "worker=ollama" in msg
    assert "→" in msg


def test_result_text_uses_error_ux():
    from ui.result_text import extract_result_text

    data = {
        "status": "ERROR",
        "result": {
            "ok": False,
            "worker": "aider",
            "error": "false_DONE: collected 0 items",
        },
    }
    text = extract_result_text(data)
    assert "false_DONE" in text or "пустой" in text.lower() or "тест" in text.lower()
    assert "Traceback" not in text


def test_task_result_format_human_error_path():
    from core.task_result import build_task_result

    row = {
        "id": "t2",
        "status": "ERROR",
        "result": {
            "ok": False,
            "worker": "aider",
            "error": "TimeoutExpired after 120s",
            "verification": {"passed": False, "summary": "Verify FAIL"},
        },
    }
    tr = build_task_result(row)
    human = tr.format_human()
    assert "Timeout" in human or "timeout" in human.lower() or "ожидания" in human
    assert "File \"" not in human
