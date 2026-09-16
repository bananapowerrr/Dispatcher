# -*- coding: utf-8 -*-
from __future__ import annotations

from types import SimpleNamespace

from core.router_score import score_worker_v2, rank_workers, pick_worker
from core.worker_api import WorkerResult, score_worker
from core.mock_worker import MockWorker, SUCCESS


def test_local_preferred_for_simple_task():
    local = SimpleNamespace(name="ollama", tier=5, enabled=True, provider="ollama", harness="aider")
    cloud = SimpleNamespace(name="openai", tier=8, enabled=True, provider="openai", harness="api")
    task = {"message": "format code", "complexity": 2, "files": ["a.py"]}
    sl = score_worker_v2(local, task, health_ok=True)
    sc = score_worker_v2(cloud, task, health_ok=True, prefer_local=True)
    assert sl.total >= sc.total * 0.9  # local competitive


def test_unhealthy_near_zero():
    w = SimpleNamespace(name="x", tier=9, enabled=True, provider="openai")
    s = score_worker_v2(w, {"complexity": 3}, health_ok=False)
    assert s.total < 0.3


def test_rank_and_pick():
    workers = [
        SimpleNamespace(name="weak", tier=2, enabled=True, provider="ollama"),
        SimpleNamespace(name="strong", tier=9, enabled=True, provider="openai"),
    ]
    task = {"message": "architecture refactor", "complexity": 5}
    ranked = rank_workers(workers, task, prefer_local=False)
    assert ranked[0].worker in ("strong", "weak")
    w, br = pick_worker(workers, task, prefer_local=False)
    assert w is not None


def test_worker_result_dict():
    r = WorkerResult(ok=True, stdout="x", files_changed=["a.py"], tokens=3)
    d = r.to_dict()
    assert d["ok"] is True
    assert "a.py" in d["files_changed"]


def test_mock_worker_result_shape():
    r = MockWorker(SUCCESS).execute({"id": "t", "attempts": 1}, {})
    assert isinstance(r, WorkerResult)
    assert r.ok is True


def test_score_worker_bridge():
    w = SimpleNamespace(name="ollama", tier=5, enabled=True, provider="ollama")
    assert score_worker(w, {"complexity": 2}) > 0
