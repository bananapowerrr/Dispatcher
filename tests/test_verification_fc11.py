# -*- coding: utf-8 -*-
"""FC-11: Verification 1.0 — FAIL ≠ DONE, gate matrix, report embed."""
from __future__ import annotations

from core.verification_engine import (
    CheckResult,
    VerificationReport,
    gate_done,
    embed_report,
    report_from_dict,
    summarize_risk,
    finalize_report,
)


def test_gate_done_fail_never_done():
    rep = VerificationReport(
        passed=False,
        checks=[CheckResult("pytest", False, detail="1 failed")],
        reason="pytest failed",
    )
    ok, reason = gate_done(True, rep)
    assert ok is False
    assert "fail" in reason.lower() or "pytest" in reason.lower()


def test_gate_done_missing_report_fail_closed():
    ok, reason = gate_done(True, None)
    assert ok is False
    assert reason == "verification_missing"


def test_gate_done_execution_fail():
    rep = VerificationReport(passed=True, checks=[CheckResult("syntax", True)])
    ok, reason = gate_done(False, rep)
    assert ok is False
    assert reason == "execution_failed"


def test_gate_done_success():
    rep = VerificationReport(
        passed=True,
        checks=[CheckResult("syntax", True), CheckResult("pytest", True)],
        reason="all_passed",
    )
    ok, reason = gate_done(True, rep)
    assert ok is True
    assert reason == "ok"


def test_short_circuit_overridden_by_fail_report():
    rep = VerificationReport(passed=False, reason="still_failed")
    ok, reason = gate_done(True, rep, short_circuit="skill_success")
    assert ok is False


def test_short_circuit_ok_without_fail():
    ok, reason = gate_done(True, None, short_circuit="cache_hit")
    assert ok is True
    assert "cache_hit" in reason


def test_embed_report_forces_error_status():
    result = {"ok": True, "worker": "aider"}
    rep = VerificationReport(
        passed=False,
        checks=[CheckResult("pytest", False, detail="boom")],
        reason="pytest failed",
    )
    out = embed_report(result, rep)
    assert out["ok"] is False
    assert out["status"] == "ERROR"
    assert out["verification"]["passed"] is False
    assert "pytest" in (out.get("error") or out["verification"].get("summary") or "")


def test_report_roundtrip_dict():
    rep = finalize_report(
        VerificationReport(
            passed=False,
            checks=[CheckResult("syntax", False, detail="SyntaxError")],
            reason="syntax failed",
            duration_sec=1.5,
        )
    )
    d = rep.to_dict()
    assert d["summary"].startswith("Verify FAIL")
    assert d["risk"] == "high"
    back = report_from_dict(d)
    assert back is not None
    assert back.passed is False
    assert back.checks[0].name == "syntax"
    assert back.duration_sec == 1.5


def test_summarize_risk_pytest_medium():
    rep = VerificationReport(
        passed=False,
        checks=[CheckResult("pytest", False)],
    )
    assert summarize_risk(rep) == "medium"


def test_task_result_verify_fail_not_done():
    from core.task_result import build_task_result

    row = {
        "id": "t-vfail",
        "message": "change code",
        "status": "DONE",  # stale status — must be corrected
        "metadata": {
            "verification_report": {
                "passed": False,
                "reason": "pytest failed",
                "summary": "Verify FAIL (0/1): pytest",
                "risk": "medium",
                "checks": [{"name": "pytest", "passed": False, "detail": "1 failed"}],
            }
        },
        "result": {"ok": True, "worker": "aider"},
    }
    tr = build_task_result(row)
    assert tr.ok is False
    assert tr.status == "ERROR"
    assert tr.verification.get("passed") is False
