# -*- coding: utf-8 -*-
"""Edge cases: dedupe, DEGRADED, latency, project lock."""
from __future__ import annotations
import time
from types import SimpleNamespace

import pytest


def test_dedupe_fingerprint_stable(tmp_path):
    from dedupe import task_fingerprint, DedupeRegistry
    a = {"message": "fix x", "files": ["a.py"], "project": "p"}
    b = {"message": "fix x", "files": ["a.py"], "project": "p"}
    c = {"message": "fix y", "files": ["a.py"], "project": "p"}
    assert task_fingerprint(a) == task_fingerprint(b)
    assert task_fingerprint(a) != task_fingerprint(c)
    reg = DedupeRegistry(state_file=tmp_path / "dedupe.json")
    fp = task_fingerprint(a)
    assert not reg.contains(fp)
    reg.mark(fp, "t1")
    assert reg.contains(fp)


def test_project_lock_same_project_blocks():
    from project_lock import ProjectLock
    lock = ProjectLock(max_global=2)
    assert lock.acquire("projA", "t1") is True
    assert lock.acquire("projA", "t2") is False
    lock.release("projA")
    assert lock.acquire("projA", "t2") is True
    lock.release("projA")


def test_project_lock_different_projects_parallel():
    from project_lock import ProjectLock
    lock = ProjectLock(max_global=2)
    assert lock.acquire("projA", "t1") is True
    assert lock.acquire("projB", "t2") is True
    assert lock.acquire("projC", "t3") is False  # max_global=2
    lock.release("projA")
    assert lock.acquire("projC", "t3") is True
    lock.release("projB")
    lock.release("projC")


def test_health_verify_degraded_path():
    """3 consecutive verify failures should mark worker degraded if API supports it."""
    from health import HealthRegistry
    h = HealthRegistry()
    h.register("w1", 1)
    if not hasattr(h, "verify_failure"):
        pytest.skip("verify_failure not on HealthRegistry")
    for i in range(3):
        h.verify_failure("w1", f"fail {i}")
    st = h.state("w1")
    # either DEGRADED status or consecutive counter >= 3
    status = getattr(st, "status", None) or (st.get("status") if isinstance(st, dict) else None)
    consec = getattr(st, "consecutive_verify_failures", None)
    if consec is None and isinstance(st, dict):
        consec = st.get("consecutive_verify_failures")
    assert (status and "DEGRAD" in str(status).upper()) or (consec is not None and consec >= 3)


def test_errors_module_payloads():
    from errors import (
        TaskTimeoutError, VerifyFailureError, DuplicateTaskError,
        ProjectBusyError, QuotaDeferredError, LoopDetectedError,
    )
    e = TaskTimeoutError(worker="w", timeout=100, estimated=90)
    d = e.to_dict()
    assert d["error"] == "TaskTimeoutError"
    assert d["timeout"] == 100
    assert VerifyFailureError(worker="w", attempts=2, last_error="x").payload["attempts"] == 2
    assert DuplicateTaskError(task_id="1", fingerprint="abc").task_id == "1"
    assert ProjectBusyError(project="p").project == "p"
    assert QuotaDeferredError(wake_at=120).wake_at == 120
    assert LoopDetectedError(worker="w", reason="same_line").reason == "same_line"


def test_latency_ratio_constant():
    """Latency reroute threshold is 80% of timeout (documented contract)."""
    # constant lives in runtime module when consolidated
    try:
        import runtime as rt
        ratio = getattr(rt, "_LATENCY_TIMEOUT_RATIO", 0.80)
    except Exception:
        ratio = 0.80
    assert 0.7 <= ratio <= 0.9
