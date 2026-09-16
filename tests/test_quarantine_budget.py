# -*- coding: utf-8 -*-
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace


def test_quarantine_exhausted_task_writes_file(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTBUS_BUS_ROOT", str(tmp_path))
    # config may already be imported — set BUS_ROOT if mutable
    import core.config as cfg
    monkeypatch.setattr(cfg, "BUS_ROOT", tmp_path, raising=False)

    from core.runtime import Runtime

    rt = Runtime.__new__(Runtime)
    rt.worker_id = "test-worker"
    rt.log = SimpleNamespace(write=lambda s: None)
    rt._emit = lambda *a, **k: None
    rt._rollback_task = lambda *a, **k: None

    task = SimpleNamespace(
        id="t-q1",
        channel="gpt",
        project="demo",
        message="fail please",
        files=["a.py"],
        attempts=3,
        verify=["pytest -q"],
        metadata={"consecutive_verify_fails": 3},
    )
    path = rt._quarantine_exhausted_task(
        task,
        reason="VERIFY_BUDGET_EXHAUSTED test",
        category="TEST_ERROR",
        gitops=None,
        before_snapshot=None,
        extra={"final": "BLOCKED"},
    )
    assert path is not None
    assert path.is_file()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["id"] == "t-q1"
    assert data["metadata"].get("quarantined") is True
    assert "VERIFY_BUDGET" in data["error"]
