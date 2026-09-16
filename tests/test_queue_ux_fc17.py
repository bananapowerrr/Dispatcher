# -*- coding: utf-8 -*-
"""FC-17: queue snapshot (no GUI)."""
from __future__ import annotations

import json
from pathlib import Path


def test_collect_queue_snapshot(tmp_path, monkeypatch):
    # isolate agentbus root
    root = tmp_path / "AgentBus"
    (root / ".agentbus" / "desktop_queue").mkdir(parents=True)
    (root / "channels" / "desktop" / "incoming").mkdir(parents=True)
    (root / "channels" / "desktop" / "processing").mkdir(parents=True)
    (root / "channels" / "desktop" / "deferred").mkdir(parents=True)

    task = {"id": "q1", "message": "hello from chat", "status": "PENDING"}
    (root / ".agentbus" / "desktop_queue" / "q1.json").write_text(
        json.dumps(task), encoding="utf-8"
    )
    (root / "channels" / "desktop" / "incoming" / "t2.json").write_text(
        json.dumps({"id": "t2", "message": "filebus task"}), encoding="utf-8"
    )
    (root / "channels" / "desktop" / "deferred" / "t3.json").write_text(
        json.dumps({"id": "t3", "message": "wait", "result": {"error": "DEFERRED_QUOTA"}}),
        encoding="utf-8",
    )

    import ui.queue_panel as qp
    monkeypatch.setattr(qp, "agentbus_root", lambda: root)

    snap = qp.collect_queue_snapshot()
    counts = snap["counts"]
    assert counts["incoming"] >= 1
    assert counts["deferred"] >= 1
    assert any("hello" in str(i.get("message")) for i in snap["items"])
    summary = qp.format_queue_summary(counts)
    # FC-21: i18n summary (RU/EN)
    assert isinstance(summary, str) and len(summary) > 5
    assert (
        str(counts.get("deferred", 0)) in summary
        or "deferred" in summary.lower()
        or "отлож" in summary.lower()
    )
