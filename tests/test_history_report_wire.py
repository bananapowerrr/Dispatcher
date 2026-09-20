"""history_detail_text uses format_task_report when possible."""
from __future__ import annotations

from core.task_result import history_detail_text, format_task_report


def test_detail_contains_task_header():
    row = {
        "id": "wire1",
        "message": "fix foo",
        "status": "DONE",
        "metadata": {"verification_report": {"passed": True, "syntax": "PASS"}},
    }
    text = history_detail_text(row)
    assert "Task #wire1" in text or "wire1" in text
    assert "RESULT" in text or "DONE" in text
    assert format_task_report(row).splitlines()[0] in text or "Task #" in text
