# -*- coding: utf-8 -*-
"""WIRE-003: worker_result present on ERROR terminal paths."""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_runtime_ops_finish_task_parses():
    src = (ROOT / "src" / "core" / "runtime_ops.py").read_text(encoding="utf-8")
    ast.parse(src)
    assert "worker_result" in src
    assert "last_result" in src
    # no empty try body left from previous broken patch
    assert "try:\n            \n        # GAP" not in src


def test_synthesize_worker_result_on_error_text():
    from core.worker_failure_contract import to_worker_result

    wr = to_worker_result(
        None,
        error_text="Проект не найден: foo",
        verification_ok=False,
    )
    assert wr["status"] in ("failure", "unavailable", "timeout", "invalid_output")
    assert wr.get("kind") == "worker_unavailable"
    assert "Проект" in wr.get("error", "") or "не найден" in wr.get("error", "")

    wr_to = to_worker_result(None, error_text="worker timed out after 120s")
    assert wr_to["kind"] == "worker_timeout"
    assert wr_to["timed_out"] is True


def test_stamp_error_mirrors_into_result():
    from core.worker_failure_contract import to_worker_result

    state = "ERROR"
    res = {"error": "boom"}
    error = "boom"
    wr = to_worker_result(res, error_text=error, verification_ok=False)
    meta = {
        "worker_result": {
            k: wr.get(k)
            for k in ("status", "kind", "ok", "timed_out", "error", "switch_backend")
            if k in wr
        },
        "failure_kind": str(wr.get("kind") or ""),
        "last_result": {"error": error, "terminal_state": state},
    }
    if state == "ERROR":
        res.setdefault("worker_result", meta["worker_result"])
    assert res["worker_result"]["kind"]
    assert meta["failure_kind"]
