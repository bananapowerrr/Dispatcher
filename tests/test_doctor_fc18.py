# -*- coding: utf-8 -*-
"""FC-18: doctor product report."""
from __future__ import annotations

from core.doctor import run_doctor, doctor_text, DoctorReport, Check


def test_run_doctor_returns_report():
    rep = run_doctor()
    assert isinstance(rep, DoctorReport)
    assert len(rep.checks) >= 3
    d = rep.to_dict()
    assert "verdict" in d
    assert d["verdict"] in ("READY", "BLOCKED")
    assert isinstance(d["checks"], list)


def test_format_human_has_verdict():
    rep = DoctorReport(
        checks=[
            Check("workers_yaml", True, True, "ok path"),
            Check("worker_capacity", False, True, "no workers"),
            Check("ui_deps", True, False, "customtkinter OK"),
        ]
    )
    text = rep.format_human()
    assert "НУЖНЫ ИСПРАВЛЕНИЯ" in text or "✗" in text
    assert "воркер" in text.lower() or "worker" in text.lower() or "Что сделать" in text
    assert "критично" in text


def test_format_human_ready():
    rep = DoctorReport(
        checks=[
            Check("workers_yaml", True, True, "ok"),
            Check("worker_capacity", True, True, "aider"),
        ]
    )
    text = rep.format_human()
    assert "ГОТОВО" in text
    assert "dispatcher" in text


def test_doctor_text_smoke():
    text = doctor_text()
    assert isinstance(text, str)
    assert len(text) > 20
