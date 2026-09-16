# -*- coding: utf-8 -*-
from __future__ import annotations


def test_clamp_timeout_hard_cap(monkeypatch):
    monkeypatch.setenv("AGENTBUS_EXEC_HARD_CAP", "120")
    from core import executor as ex
    # reload clamp if already imported with old env - call functions directly
    assert ex._clamp_timeout(9999) == 120
    assert ex._clamp_timeout(30) == 30
    assert ex._clamp_timeout(5) == 15  # minimum floor


def test_discard_is_surgical_not_hard_reset():
    """Regression: discard_task_changes must not use reset --hard."""
    import inspect
    from safety import gitops
    src = inspect.getsource(gitops.GitOps.discard_task_changes)
    assert "reset" not in src.lower() or "reset --hard" not in src
    assert "checkout" in src


def test_cleanup_task_branch_api_exists():
    from safety.gitops import GitOps
    assert hasattr(GitOps, "cleanup_task_branch")
    assert hasattr(GitOps, "prune_stale_agentbus_branches")
