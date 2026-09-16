# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path

from skills.builtin.formatting import format_code, sort_imports
from utils.task_trace import TaskTrace, TraceStore


def test_format_code_missing_tools(tmp_path: Path):
    r = format_code(root=tmp_path, target=str(tmp_path))
    assert r.get("formatted") is True
    assert "steps" in r


def test_trace_lifecycle(tmp_path: Path):
    store = TraceStore(path=tmp_path / "traces.jsonl")
    tr = store.start("t1", project_id="p", worker_id="mock")
    tr.add("ROUTER_DECISION", worker="mock")
    tr.add("WORKER_FINISHED", ok=True)
    tr.add("VERIFY_PASSED")
    done = store.complete("t1", "DONE")
    assert done is not None
    assert done.final_status == "DONE"
    assert "TASK_STARTED" in [e.name for e in done.events]
    assert (tmp_path / "traces.jsonl").is_file()
    assert "t1" in done.summary_line()


def test_registry_format_delegates(tmp_path: Path):
    from skills.skills import SkillRegistry
    from skills.tools import ToolRegistry
    reg = SkillRegistry(ToolRegistry(project_root=str(tmp_path)))
    (tmp_path / "a.py").write_text("import os\nx=1\n", encoding="utf-8")
    # execute format_code skill if registered
    if "format_code" in getattr(reg, "skills", {}) or hasattr(reg, "_format_code"):
        r = reg._format_code(path=str(tmp_path))
        assert "steps" in r or r.get("formatted")
