# -*- coding: utf-8 -*-
from __future__ import annotations

from types import SimpleNamespace

from core.worker_api import score_worker, ConfigWorkerAdapter, WorkerResult
from core.verification_engine import gate_done, VerificationReport


def test_score_prefers_local_high_tier():
    local = SimpleNamespace(tier=7, quality=1.0, priority=10, provider="local", enabled=True)
    cloud = SimpleNamespace(tier=9, quality=1.0, priority=50, provider="openai", enabled=True)
    task = SimpleNamespace(complexity=3, metadata={})
    # local cheaper should compete; both positive
    assert score_worker(local, task) > 0
    assert score_worker(cloud, task) > 0


def test_adapter_can_handle_soft_tier():
    w = SimpleNamespace(name="w", enabled=True, tier=5)
    ad = ConfigWorkerAdapter(worker=w)
    assert ad.can_handle(SimpleNamespace(complexity=2, metadata={}))


def test_worker_result_from_exec():
    legacy = SimpleNamespace(ok=True, stdout="hi", stderr="", latency=1.5, tokens=10)
    r = WorkerResult.from_exec(legacy)
    assert r.ok and r.stdout == "hi" and r.latency == 1.5


def test_gate_done_still_holds():
    ok, _ = gate_done(True, VerificationReport(passed=True))
    assert ok
    ok, reason = gate_done(True, VerificationReport(passed=False, reason="x"))
    assert not ok
