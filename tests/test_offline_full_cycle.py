# -*- coding: utf-8 -*-
"""P1.7 — offline full cycle: desktop queue → claim → processing → done."""
from __future__ import annotations

import json
from pathlib import Path


def test_desktop_queue_claim_and_bus_done(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".agentbus").mkdir()
    bus_root = tmp_path / "bus"
    spill = tmp_path / ".agentbus" / "desktop_queue"

    from core.local_queue import LocalQueue, enqueue_desktop_task
    from core import local_queue as lq
    from core.bus import FileBus

    lq._GLOBAL = LocalQueue(spill_dir=spill)
    tid = enqueue_desktop_task(
        "format imports in demo",
        project="demo",
        files=["demo.py"],
        root=tmp_path,
    )
    assert tid
    raw = lq._GLOBAL.claim()
    assert raw is not None
    assert raw["channel"] == "desktop"
    assert raw["message"]

    # Simulate runtime seed into bus processing → done
    bus = FileBus(bus_root, ("desktop",))
    bus.ensure()
    raw["status"] = "PROCESSING"
    name = f"{raw['id']}.json"
    proc = bus_root / "channels" / "desktop" / "processing" / name
    proc.parent.mkdir(parents=True, exist_ok=True)
    proc.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")

    raw["status"] = "DONE"
    raw["result"] = {"ok": True, "via": "offline_mock", "skill": "sort_imports"}
    proc.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
    assert bus.move("desktop", "processing", "done", name)

    done = bus_root / "channels" / "desktop" / "done" / name
    assert done.is_file()
    data = json.loads(done.read_text(encoding="utf-8"))
    assert data["status"] == "DONE"
    assert data["result"]["ok"] is True


def test_filebus_incoming_to_done_harness(tmp_path):
    from core.e2e_harness import (
        ensure_bus_channels,
        write_task,
        claim_task,
        finish_task,
    )

    bus_root = tmp_path / "bus"
    ensure_bus_channels(bus_root, "gpt")
    write_task(
        bus_root,
        task_id="t-cycle-1",
        message="noop offline",
        files=[],
        channel="gpt",
        project="p",
        metadata={"source": "e2e", "complexity": 1},
    )
    claim_task(bus_root, "t-cycle-1", channel="gpt")
    finish_task(
        bus_root,
        "t-cycle-1",
        channel="gpt",
        state="done",
        extra={"status": "DONE", "result": {"ok": True}},
    )
    done = bus_root / "channels" / "gpt" / "done" / "t-cycle-1.json"
    assert done.is_file()
    assert json.loads(done.read_text(encoding="utf-8"))["status"] == "DONE"


def test_verify_policy_blocks_empty_verify_on_hard_task():
    from core.verify_policy import apply_verify_policy, ladder_summary

    raw = apply_verify_policy({
        "message": "deep refactor",
        "files": ["a.py", "b.py", "c.py"],
        "verify": [],
        "metadata": {"complexity": 5, "source": "autopilot"},
    })
    assert raw.get("verify")
    assert "pytest" in " ".join(raw["verify"]).lower()
    assert "L3" in ladder_summary(raw) or "ladder" in ladder_summary(raw)
