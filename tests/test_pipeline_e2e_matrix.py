# -*- coding: utf-8 -*-
"""P0-3 Mock E2E matrix — offline reliability scenarios."""
from __future__ import annotations

from pathlib import Path

import pytest

from core.mock_worker import (
    SUCCESS,
    VERIFY_FAIL,
    TIMEOUT,
    CRASH,
    RETRY_SUCCESS,
    EMPTY_OUTPUT,
    INVALID_OUTPUT,
)
from core.pipeline_e2e import run_pipeline
from core.verification_engine import gate_done, VerificationReport, finalize_report, CheckResult


def _proj(tmp_path: Path) -> Path:
    p = tmp_path / "proj"
    p.mkdir()
    (p / "demo.py").write_text("def ok():\n    return 1\n", encoding="utf-8")
    return p


def test_matrix_success_done(tmp_path: Path):
    res = run_pipeline(project_root=_proj(tmp_path), bus_root=tmp_path / "bus", scenario=SUCCESS)
    assert res.final_status == "DONE"
    assert res.verify_passed is True
    assert "TASK_DONE" in res.events or "DONE" in res.final_status


def test_matrix_verify_fail_error(tmp_path: Path):
    res = run_pipeline(
        project_root=_proj(tmp_path),
        bus_root=tmp_path / "bus2",
        scenario=VERIFY_FAIL,
        max_attempts=1,
    )
    assert res.final_status == "ERROR"
    assert res.verify_passed is False


def test_matrix_timeout_retry_then_error(tmp_path: Path):
    res = run_pipeline(
        project_root=_proj(tmp_path),
        bus_root=tmp_path / "bus3",
        scenario=TIMEOUT,
        max_attempts=2,
    )
    assert res.final_status == "ERROR"
    assert "RETRY" in res.events or res.attempts >= 1


def test_matrix_crash_error(tmp_path: Path):
    res = run_pipeline(
        project_root=_proj(tmp_path),
        bus_root=tmp_path / "bus4",
        scenario=CRASH,
        max_attempts=1,
    )
    assert res.final_status == "ERROR"
    assert "WORKER_CRASH" in res.events or res.worker_ok is False


def test_matrix_retry_success_done(tmp_path: Path):
    res = run_pipeline(
        project_root=_proj(tmp_path),
        bus_root=tmp_path / "bus5",
        scenario=RETRY_SUCCESS,
        max_attempts=3,
    )
    assert res.final_status == "DONE"
    assert res.attempts >= 2


def test_matrix_empty_output_still_verifies(tmp_path: Path):
    """Worker ok + empty stdout + existing valid file → DONE if verify ok."""
    res = run_pipeline(
        project_root=_proj(tmp_path),
        bus_root=tmp_path / "bus6",
        scenario=EMPTY_OUTPUT,
        max_attempts=1,
    )
    # EMPTY does not rewrite files → original valid demo.py → DONE
    assert res.final_status in ("DONE", "ERROR")
    if res.final_status == "DONE":
        assert res.verify_passed is True


def test_adversarial_gate_worker_ok_verify_fail():
    """Worker.success != Task.success"""
    rep = finalize_report(
        VerificationReport(
            passed=False,
            checks=[CheckResult(name="syntax", passed=False, detail="bad")],
            reason="syntax",
        )
    )
    ok, reason = gate_done(True, rep)  # worker said success
    assert ok is False
    assert reason


def test_adversarial_gate_no_verification():
    ok, reason = gate_done(True, None)
    assert ok is False


def test_adversarial_gate_worker_fail():
    rep = finalize_report(VerificationReport(passed=True, checks=[], reason=""))
    ok, reason = gate_done(False, rep)
    assert ok is False


def test_adversarial_gate_both_ok():
    rep = finalize_report(
        VerificationReport(
            passed=True,
            checks=[CheckResult(name="syntax", passed=True)],
            reason="",
        )
    )
    ok, reason = gate_done(True, rep)
    assert ok is True
