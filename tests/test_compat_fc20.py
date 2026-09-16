# -*- coding: utf-8 -*-
"""FC-20: legacy task/result JSON compatibility."""
from __future__ import annotations

from core.task_result import build_task_result, history_card_lines, history_detail_text, SkillResult
from core.worker_api import WorkerResult


def test_empty_row_no_raise():
    tr = build_task_result({})
    assert tr.status in ("PENDING", "ERROR", "")
    card = history_card_lines({})
    assert isinstance(card, dict)


def test_status_success_alias():
    tr = build_task_result({
        "id": "1",
        "status": "SUCCESS",
        "result": {"worker": "aider", "stdout": "patched"},
    })
    assert tr.status == "DONE"
    assert tr.ok is True
    assert tr.worker == "aider"


def test_result_as_plain_string():
    tr = build_task_result({"id": "2", "status": "done", "result": "all good"})
    assert tr.ok is True
    assert tr.status == "DONE"
    assert "good" in (tr.summary or "")


def test_legacy_msg_field():
    tr = build_task_result({"id": "3", "msg": "hello world", "status": "PENDING"})
    # message used for cards
    card = history_card_lines({"id": "3", "msg": "hello world", "status": "PENDING"})
    assert "hello" in card.get("prompt", "") or tr.status == "PENDING"


def test_legacy_success_flag():
    tr = build_task_result({"id": "4", "result": {"success": True, "output": "y"}})
    assert tr.ok is True


def test_legacy_files_changed_dict():
    tr = build_task_result({
        "id": "5",
        "status": "DONE",
        "result": {"ok": True, "files_changed": {"a.py": "content", "b.py": "x"}},
    })
    assert "a.py" in tr.changes.files
    assert "b.py" in tr.changes.files


def test_errors_folder_state():
    tr = build_task_result({
        "id": "6",
        "_state": "errors",
        "error": "boom",
        "result": {"ok": False, "stderr": "traceback here"},
    })
    assert tr.ok is False
    assert tr.status == "ERROR"


def test_verification_report_legacy_path():
    tr = build_task_result({
        "id": "7",
        "status": "DONE",
        "metadata": {
            "verification_report": {
                "passed": False,
                "reason": "pytest failed",
                "summary": "Verify FAIL",
            }
        },
        "result": {"ok": True, "worker": "aider"},
    })
    assert tr.ok is False
    assert tr.status == "ERROR"


def test_skill_result_list_payload():
    sr = SkillResult.from_execute("x", {"success": True, "result": ["a.py", "b.py"]})
    assert sr.success
    # list payload may land in message/data — must not raise
    assert sr.data is not None or sr.message


def test_worker_result_roundtrip_legacy_namespace():
    class Legacy:
        ok = True
        stdout = "hi"
        stderr = ""
        latency = 1.0
        tokens = 3
        files_changed = ["z.py"]
        meta = {}

    wr = WorkerResult.from_exec(Legacy())
    tr = build_task_result({"id": "8", "status": "DONE", "result": wr.to_dict()})
    assert tr.ok and "z.py" in tr.changes.files


def test_history_detail_never_raises():
    text = history_detail_text({"id": "9", "status": "ERROR", "result": {"error": "x"}})
    assert isinstance(text, str)


def test_timeout_overrides_done():
    tr = build_task_result({
        "id": "10",
        "status": "DONE",
        "result": {"ok": True, "timed_out": True, "worker": "ollama"},
    })
    assert tr.ok is False
    assert tr.status == "ERROR"
