"""format_task_report offline."""
from __future__ import annotations

from core.task_result import format_task_report


def test_report_sections():
    row = {
        "id": "abc123",
        "message": "add docstring to app.py",
        "status": "DONE",
        "metadata": {
            "worker": "mock",
            "duration_sec": 1.5,
            "plan_step_id": "s4",
            "verification_report": {"syntax": "PASS", "tests": "PASS", "passed": True},
            "files_changed": ["app.py"],
        },
    }
    text = format_task_report(row)
    assert "Task #abc123" in text
    assert "REQUEST" in text
    assert "WORKER" in text
    assert "CHANGES" in text
    assert "VERIFY" in text
    assert "RESULT" in text
    assert "DONE" in text


def test_report_error_not_ok():
    row = {
        "id": "e1",
        "message": "bad",
        "status": "ERROR",
        "error": "verify failed",
        "metadata": {"verification_report": {"passed": False, "summary": "FAIL"}},
    }
    text = format_task_report(row)
    assert "ERROR" in text
    assert "verify" in text.lower() or "FAIL" in text
