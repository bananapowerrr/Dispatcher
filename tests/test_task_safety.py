# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path


def test_resolve_git_policy_autopilot_forces_branch():
    from core.task_safety import resolve_git_policy

    task = {"metadata": {"source": "autopilot", "complexity": 2}}
    assert resolve_git_policy(task, default="park") == "branch"


def test_resolve_git_policy_high_complexity():
    from core.task_safety import resolve_git_policy

    task = {"metadata": {"source": "ui", "complexity": 5}}
    assert resolve_git_policy(task, default="park") == "branch"


def test_resolve_git_policy_explicit_wins():
    from core.task_safety import resolve_git_policy

    task = {"metadata": {"source": "autopilot", "git_policy": "allow"}}
    assert resolve_git_policy(task, default="park") == "allow"


def test_diff_limits_autopilot_tighter():
    from core.task_safety import diff_limits_for_task, DIFF_MAX_FILES_AUTO

    auto = {"metadata": {"source": "autopilot"}}
    ui = {"metadata": {"source": "ui", "complexity": 2}}
    af, al = diff_limits_for_task(auto)
    uf, ul = diff_limits_for_task(ui)
    assert af <= uf
    assert al <= ul
    assert af == DIFF_MAX_FILES_AUTO


def test_check_diff_budget_files(tmp_path):
    from core.task_safety import check_diff_budget

    # no git repo needed if we only check file count against empty stage... 
    # with many paths and no git, lines=0 but files count still applies
    paths = [f"f{i}.py" for i in range(30)]
    task = {"metadata": {"source": "autopilot"}}
    r = check_diff_budget(root=str(tmp_path), stage_paths=paths, task=task)
    assert r["ok"] is False
    assert "files" in r["reason"]


def test_autopilot_payload_git_policy():
    from skills.autopilot import GeneratedTask

    t = GeneratedTask(message="x", files=["a.py"], priority=4, category="c")
    p = t.to_bus_payload(project="p")
    assert p["metadata"].get("git_policy") == "branch"
    assert p["verify"]
