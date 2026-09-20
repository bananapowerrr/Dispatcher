# -*- coding: utf-8 -*-
"""Day-3 offline: context pack budget + git safety rules."""
from __future__ import annotations

from intelligence.context_budget import (
    ContextAssembly,
    SlotSpec,
    assemble_worker_message,
    estimate_tokens,
    smart_truncate,
)
from intelligence.context_pack import pack_for_worker, is_context_safe_for_7b, PACK_TOTAL
from safety.git_safety import (
    branch_delete_allowed,
    forbid_reset_hard,
    paths_safe_to_commit,
    paths_safe_to_discard,
)


def test_smart_truncate_keeps_tail():
    text = "A" * 500 + "MIDDLE" + "B" * 500
    out = smart_truncate(text, 200, keep_tail=True)
    assert len(out) <= 200
    assert "truncated" in out or "..." in out


def test_assemble_under_budget():
    huge = "x" * 50_000
    body = assemble_worker_message(
        user_request="fix the bug",
        memory=huge,
        conversation=huge,
        rag=huge,
        active_diff=huge,
        extras=huge,
        system_rules="be careful",
        total_chars=8_000,
    )
    assert len(body) <= 8_000 + 50  # small overhead tolerance
    assert "USER REQUEST" in body or "fix the bug" in body


def test_estimate_tokens_positive():
    assert estimate_tokens("hello") >= 1
    assert estimate_tokens("привет мир") >= 1


def test_pack_for_worker_without_project():
    res = pack_for_worker(
        user_message="Создай test_aider.txt",
        project_memory="use pytest",
        conversation_tail="user: hi\nagent: ok",
        total_chars=5_000,
    )
    assert res.message
    assert res.stats["chars"] <= 5_000
    assert is_context_safe_for_7b(res, max_chars=5_000)


def test_context_assembly_drops_low_priority():
    asm = ContextAssembly(total_chars=500)
    asm.specs["extras"] = SlotSpec("extras", max_chars=400, priority=10)
    asm.specs["user_request"] = SlotSpec("user_request", max_chars=400, min_chars=50, priority=100)
    asm.set("extras", "E" * 400)
    asm.set("user_request", "do the thing")
    body = asm.assemble()
    assert "do the thing" in body
    assert len(body) <= 500 + 20


def test_commit_blocked_on_outside():
    d = paths_safe_to_commit(
        stage=["src/a.py"],
        outside=["secrets.env"],
        conflicted=[],
    )
    assert d.ok is False
    assert d.action == "block"


def test_commit_ok_task_only():
    d = paths_safe_to_commit(stage=["a.py", "b.py"], outside=[], conflicted=[])
    assert d.ok is True
    assert d.action == "commit"
    assert d.paths == ["a.py", "b.py"]


def test_discard_skips_user_dirty():
    d = paths_safe_to_discard(
        created=["new_by_agent.py"],
        changed=["user_was_editing.py"],
        baseline_modified=["user_was_editing.py"],
        baseline_untracked=[],
        conflicted=[],
    )
    assert "new_by_agent.py" in d.paths
    assert "user_was_editing.py" in d.skipped
    assert "user_was_editing.py" not in d.paths


def test_discard_skips_conflicted():
    d = paths_safe_to_discard(
        created=[],
        changed=["shared.py"],
        baseline_modified=[],
        baseline_untracked=[],
        conflicted=["shared.py"],
    )
    assert d.paths == []
    assert "shared.py" in d.skipped


def test_never_reset_hard_policy():
    assert forbid_reset_hard() is True


def test_branch_delete_only_agentbus():
    assert branch_delete_allowed("agentbus/task-abc") is True
    assert branch_delete_allowed("main") is False
    assert branch_delete_allowed("feature/x") is False
