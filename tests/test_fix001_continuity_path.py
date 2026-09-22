# -*- coding: utf-8 -*-
from pathlib import Path


def test_core_task_continuity_import():
    from core.task_continuity import merge_prev_failure, continuity_for_next_prompt

    block = continuity_for_next_prompt({
        "attempts": 1,
        "result": {"error": "x", "verification": {"ok": False}, "changed_files": ["a.py"]},
    })
    assert "PREVIOUS ATTEMPT" in block
    assert merge_prev_failure("raw", {"attempts": 1, "result": {"error": "e", "changed_files": ["b.py"]}})


def test_rp_context_imports_core_or_intelligence():
    src = Path("/home/workdir/artifacts/src/core/rp_context.py").read_text(encoding="utf-8")
    assert "task_continuity" in src
    assert "merge_prev_failure" in src


def test_context_audit_attach():
    from core.context_audit_attach import attach_context_audit

    meta = attach_context_audit({}, {
        "context_audit": {
            "selected_files": ["a.py"],
            "selected_n": 1,
            "excluded_n": 2,
            "chars": 100,
            "truncated": False,
            "has_previous_failure": True,
        }
    })
    assert meta["context_audit"]["selected_n"] == 1
    assert meta["context_audit"]["has_previous_failure"] is True
