# -*- coding: utf-8 -*-
"""Task retry budget + dirty worktree preflight."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest


def test_config_verify_fail_max():
    from config import VERIFY_FAIL_MAX, DIRTY_GIT_POLICY, MAX_ATTEMPTS
    assert VERIFY_FAIL_MAX >= 1
    assert MAX_ATTEMPTS >= 1
    assert DIRTY_GIT_POLICY in ("park", "stash", "branch", "allow") or isinstance(DIRTY_GIT_POLICY, str)


def test_gitops_clean_ok(tmp_path):
    import subprocess
    from gitops import GitOps

    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True, capture_output=True)
    (tmp_path / "a.py").write_text("x=1\n", encoding="utf-8")
    subprocess.run(["git", "add", "a.py"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=tmp_path, check=True, capture_output=True)

    g = GitOps(tmp_path, enabled=True)
    info = g.ensure_worktree_ready(policy="park", task_id="t1")
    assert info["ok"] is True
    assert info["action"] in ("clean", "no_repo")


def test_gitops_dirty_park(tmp_path):
    import subprocess
    from gitops import GitOps

    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True, capture_output=True)
    (tmp_path / "a.py").write_text("x=1\n", encoding="utf-8")
    subprocess.run(["git", "add", "a.py"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=tmp_path, check=True, capture_output=True)
    (tmp_path / "a.py").write_text("x=2\n", encoding="utf-8")  # dirty

    g = GitOps(tmp_path, enabled=True)
    info = g.ensure_worktree_ready(policy="park", task_id="t2")
    assert info["ok"] is False
    assert info["action"] == "park"
    assert info["dirty_lines"]


def test_gitops_allow_dirty(tmp_path):
    import subprocess
    from gitops import GitOps

    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True, capture_output=True)
    (tmp_path / "a.py").write_text("x=1\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "i"], cwd=tmp_path, check=True, capture_output=True)
    (tmp_path / "b.py").write_text("y=1\n", encoding="utf-8")

    g = GitOps(tmp_path, enabled=True)
    info = g.ensure_worktree_ready(policy="allow", task_id="t3")
    assert info["ok"] is True
    assert info["action"] == "allow_dirty"


def test_verify_budget_logic_standalone():
    """Mirror RuntimeOps consecutive-verify counter without importing runtime."""
    from config import VERIFY_FAIL_MAX

    class FakeTask:
        def __init__(self):
            self.metadata = {}

    def bump(task, error=""):
        meta = dict(task.metadata or {})
        n = int(meta.get("consecutive_verify_fails") or 0) + 1
        meta["consecutive_verify_fails"] = n
        if error:
            meta["last_verify_error"] = error[-500:]
        task.metadata = meta
        return n

    def exhausted(task):
        n = int((task.metadata or {}).get("consecutive_verify_fails") or 0)
        return n >= int(VERIFY_FAIL_MAX)

    def reset(task):
        meta = dict(task.metadata or {})
        meta["consecutive_verify_fails"] = 0
        task.metadata = meta

    task = FakeTask()
    for i in range(VERIFY_FAIL_MAX):
        assert bump(task, "syntax") == i + 1
    assert exhausted(task) is True
    reset(task)
    assert exhausted(task) is False
