# -*- coding: utf-8 -*-
from core.doctor import run_doctor, print_doctor, DoctorReport, Check


def test_run_doctor_returns_report():
    rep = run_doctor()
    assert isinstance(rep, DoctorReport)
    assert len(rep.checks) >= 5
    ids = {c.id for c in rep.checks}
    assert "workers_yaml" in ids
    assert "desktop_queue" in ids
    assert "strict_verify" in ids


def test_print_doctor_exit_code_matches_critical(capsys):
    # synthetic report
    from core import doctor as D
    good = DoctorReport(checks=[
        Check("a", True, True, "ok"),
        Check("b", False, False, "optional"),
    ])
    assert print_doctor(good) == 0
    bad = DoctorReport(checks=[
        Check("a", False, True, "missing"),
    ])
    assert print_doctor(bad) == 1
