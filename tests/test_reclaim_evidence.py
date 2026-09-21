# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import os
import time
from pathlib import Path


def test_classify_failure_layer():
    from core.execution_evidence import classify_failure_layer

    layer, ok = classify_failure_layer(reclaim_reason="stuck_max_attempts")
    assert layer == "reclaim_max_attempts" and ok is False
    layer, ok = classify_failure_layer(reclaim_reason="stuck_no_heartbeat")
    assert layer == "reclaim_no_heartbeat" and ok is True
    layer, ok = classify_failure_layer(error="Connection refused to ollama")
    assert layer == "worker_infra" and ok is True


def test_reclaim_max_attempts_writes_evidence(tmp_path: Path):
    from core.reclaim import reclaim_stuck, write_lease

    proc = tmp_path / "processing"
    inc = tmp_path / "incoming"
    err = tmp_path / "errors"
    proc.mkdir()
    inc.mkdir()
    err.mkdir()

    task_path = proc / "t-stuck.json"
    raw = {
        "id": "t-stuck",
        "attempts": 3,
        "status": "PROCESSING",
        "metadata": {},
        "result": {},
    }
    task_path.write_text(json.dumps(raw), encoding="utf-8")
    old = time.time() - 10_000
    os.utime(task_path, (old, old))
    write_lease(
        task_path,
        task_id="t-stuck",
        worker="mock",
        complexity=1,
        attempts=3,
        stuck_timeout_sec=60,
        phase="work",
    )
    lease = task_path.with_name("t-stuck.lease.json")
    if lease.is_file():
        data = json.loads(lease.read_text(encoding="utf-8"))
        data["last_heartbeat"] = old
        lease.write_text(json.dumps(data), encoding="utf-8")
        os.utime(lease, (old, old))

    results = reclaim_stuck(
        processing_dir=proc,
        incoming_dir=inc,
        errors_dir=err,
        max_attempts=3,
        base_sec=1,
        max_sec=10,
        now=time.time(),
    )
    assert results
    err_files = list(err.glob("*.json"))
    assert err_files
    body = json.loads(err_files[0].read_text(encoding="utf-8"))
    assert body.get("status") == "ERROR"
    meta = body.get("metadata") or {}
    assert meta.get("failure_layer") == "reclaim_max_attempts"
    assert meta.get("recoverable") is False
    assert "execution_evidence" in meta
    assert meta["execution_evidence"].get("terminal_state") == "ERROR"


def test_reclaim_source_has_failure_layer():
    p = Path("/home/workdir/artifacts/src/core/reclaim.py")
    src = p.read_text(encoding="utf-8")
    assert "failure_layer" in src
    assert "recoverable" in src
    assert "execution_evidence" in src
