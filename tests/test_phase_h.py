# -*- coding: utf-8 -*-
from __future__ import annotations

import os
from pathlib import Path


def test_worktree_manager_disabled_by_default(tmp_path, monkeypatch):
    monkeypatch.delenv("AGENTBUS_GIT_WORKTREE", raising=False)
    from safety.worktree import worktree_enabled, WorktreeManager

    assert worktree_enabled() is False
    wm = WorktreeManager(tmp_path)
    info = wm.add("t1")
    assert info["ok"] is False
    assert info["reason"] == "disabled"


def test_worktree_add_remove(tmp_path, monkeypatch):
    import subprocess

    monkeypatch.setenv("AGENTBUS_GIT_WORKTREE", "1")
    subprocess.run(["git", "init"], cwd=str(tmp_path), capture_output=True, check=True)
    subprocess.run(
        ["git", "config", "user.email", "t@t"], cwd=str(tmp_path), capture_output=True
    )
    subprocess.run(
        ["git", "config", "user.name", "t"], cwd=str(tmp_path), capture_output=True
    )
    (tmp_path / "a.txt").write_text("x\n", encoding="utf-8")
    subprocess.run(["git", "add", "a.txt"], cwd=str(tmp_path), capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "i"], cwd=str(tmp_path), capture_output=True, check=True
    )

    from safety.worktree import WorktreeManager

    wm = WorktreeManager(tmp_path)
    info = wm.add("task42")
    assert info["ok"] is True, info
    assert Path(info["path"]).is_dir()
    removed = wm.remove("task42", delete_branch=True)
    assert removed.get("removed") or not Path(info["path"]).exists()


def test_signatures_snippet(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTBUS_CODEINTEL", "1")
    (tmp_path / "mod.py").write_text(
        "def alpha():\n    return 1\n\ndef beta():\n    return alpha()\n",
        encoding="utf-8",
    )
    from intelligence.code_intelligence import CodeIntelligence

    ci = CodeIntelligence(tmp_path)
    snip = ci.signatures_snippet(["mod.py"], max_chars=800)
    assert "signatures" in snip
    assert "alpha" in snip or "mod.alpha" in snip


def test_benchmark_script_runs():
    import subprocess
    import sys

    root = Path(__file__).resolve().parents[1]
    r = subprocess.run(
        [sys.executable, str(root / "scripts" / "benchmark_harness.py")],
        cwd=str(root),
        env={**os.environ, "PYTHONPATH": f"{root / 'src'}:{root}"},
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert "Pass@1" in (r.stdout or "")
