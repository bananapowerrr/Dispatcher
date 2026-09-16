# -*- coding: utf-8 -*-
"""FC-27 Dynamic Queue from Living Plan."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from intelligence.living_plan import LivingPlan, LivingStep
from intelligence.dynamic_queue import (
    sync_plan_to_queue,
    sync_from_disk,
    on_task_terminal,
    _already_emitted,
    mark_step_emitted,
)


def test_sync_emits_eligible(tmp_path, monkeypatch):
    plan = LivingPlan(
        project_id="p1",
        version=1,
        summary="demo",
        steps=[
            LivingStep(id="s1", action="first", status="DONE"),
            LivingStep(id="s2", action="second", status="PENDING", depends_on=["s1"]),
            LivingStep(id="s3", action="old", status="SUPERSEDED"),
        ],
    )
    emitted_ids: list[str] = []

    class FakeQ:
        def put(self, task):
            emitted_ids.append(str(task["id"]))
            return task["id"]

    class BoomTS:
        @staticmethod
        def submit_payload(*a, **k):
            return (None, "fail")

    monkeypatch.setitem(sys.modules, "core.task_service", BoomTS())
    import core.local_queue as lq
    monkeypatch.setattr(lq, "get_local_queue", lambda root=None: FakeQ())

    res = sync_plan_to_queue(
        plan,
        project_root=tmp_path,
        use_desktop_queue=True,
        persist=True,
    )
    assert any("s2" in x for x in res.emitted)
    assert plan.get("s2").meta.get("emitted") is True
    assert plan.get("s3").status == "SUPERSEDED"
    # second sync: no duplicate
    res2 = sync_plan_to_queue(
        plan, project_root=tmp_path, use_desktop_queue=True, persist=False
    )
    assert res2.emitted == []
    assert _already_emitted(plan.get("s2"))


def test_filebus_emit(tmp_path):
    plan = LivingPlan(
        version=1,
        steps=[LivingStep(id="a", action="do a", status="PENDING")],
    )
    res = sync_plan_to_queue(
        plan,
        project_root=tmp_path,
        use_desktop_queue=False,
        use_filebus=True,
        bus_root=tmp_path,
        persist=True,
        max_emit=2,
    )
    assert res.emitted
    incoming = tmp_path / "channels" / "autopilot" / "incoming"
    files = list(incoming.glob("*.json"))
    assert files
    data = json.loads(files[0].read_text(encoding="utf-8"))
    assert data["metadata"]["source"] == "living_plan"
    assert data["metadata"]["plan_step_id"] == "a"


def test_on_task_terminal():
    plan = LivingPlan(steps=[
        LivingStep(id="x", action="work", status="READY", meta={"task_id": "plan-1-x"}),
    ])
    assert on_task_terminal(plan, task_id="plan-1-x", status="DONE")
    assert plan.get("x").status == "DONE"


def test_sync_from_disk_empty(tmp_path):
    res = sync_from_disk(tmp_path)
    assert res.emitted == []


def test_mark_emitted_idempotent():
    s = LivingStep(id="z", action="z", status="PENDING")
    mark_step_emitted(s, "tid-1")
    assert s.meta["emitted"] and s.meta["task_id"] == "tid-1"
    assert _already_emitted(s)
