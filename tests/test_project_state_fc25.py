# -*- coding: utf-8 -*-
"""FC-24/25: ProjectState + supervisor role map."""
from __future__ import annotations

from intelligence.project_state import (
    ProjectState,
    load_project_state,
    save_project_state,
)
from intelligence.supervisor_roles import describe_roles, list_roles, modules_for


def test_roles_cover_core():
    roles = list_roles()
    for r in ("planner", "reviewer", "state", "context", "replanner"):
        assert r in roles
        assert modules_for(r)


def test_describe_roles():
    d = describe_roles()
    assert "planner" in d
    assert "pev_loop" in str(d["planner"]["modules"])


def test_project_state_roundtrip(tmp_path):
    st = ProjectState(goal="Ship AgentBus 0.10", current_phase="planning")
    st.add_constraint("local-first")
    st.add_decision("use file-bus")
    st.add_risk("no live Ollama yet")
    st.bump_plan()
    st.mark_pending("t1")
    st.mark_in_progress("t1")
    st.record_result({"task_id": "t1", "status": "DONE", "ok": True, "summary": "ok"})
    path = save_project_state(tmp_path, st)
    assert path.is_file()
    loaded = load_project_state(tmp_path)
    assert loaded.goal.startswith("Ship")
    assert loaded.plan_version >= 1
    assert "t1" in loaded.completed
    assert "local-first" in loaded.constraints
    lines = loaded.summary_lines()
    assert any("goal" in x or "Ship" in x for x in lines)


def test_from_dict_tolerates_junk():
    st = ProjectState.from_dict(
        {"goal": "x", "constraints": "bad", "plan_version": "3", "unknown": 1}
    )
    assert st.goal == "x"
    assert st.constraints == []
    assert st.plan_version == 3


def test_missing_file_empty_state(tmp_path):
    st = load_project_state(tmp_path / "nope")
    assert st.goal == ""
    assert st.plan_version == 0
