# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path

from core.mock_worker import MockWorker, SUCCESS, VERIFY_FAIL, CRASH, TIMEOUT, run_scenario
from core.pipeline_e2e import run_pipeline
from core.verification_engine import VerificationReport, finalize_report, CheckResult


def test_mock_success_scenario():
    r = run_scenario(SUCCESS)
    assert r.ok is True
    assert "mock" in (r.stdout or "").lower() or r.ok


def test_mock_crash():
    w = MockWorker(CRASH)
    try:
        w.execute({"id": "x", "attempts": 1}, {})
        assert False, "should raise"
    except RuntimeError:
        pass


def test_pipeline_success(tmp_path: Path):
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "demo.py").write_text("def ok():\n    return 1\n", encoding="utf-8")
    res = run_pipeline(project_root=proj, bus_root=tmp_path / "bus", scenario=SUCCESS)
    assert res.final_status == "DONE"
    assert "TASK_DONE" in res.events
    assert res.verify_passed is True


def test_pipeline_verify_fail(tmp_path: Path):
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "demo.py").write_text("def ok():\n    return 1\n", encoding="utf-8")
    res = run_pipeline(
        project_root=proj,
        bus_root=tmp_path / "bus",
        scenario=VERIFY_FAIL,
        max_attempts=1,
    )
    assert res.final_status == "ERROR"
    assert "VERIFY_FAILED" in res.events or res.verify_passed is False


def test_verification_report_contract():
    rep = VerificationReport(
        passed=False,
        checks=[CheckResult(name="pytest", passed=False, detail="fail", code=1)],
        reason="tests",
    )
    rep = finalize_report(rep)
    d = rep.to_dict()
    assert d["passed"] is False
    assert "risk" in d
    assert isinstance(d["checks"], list)
    assert d["checks"][0]["status"] == "failed"
    assert d["checks"][0].get("exit_code") == 1
