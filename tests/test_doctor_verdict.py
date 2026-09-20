"""doctor_verdict_line offline."""
from core.doctor import doctor_verdict_line, doctor_full_text, run_doctor

def test_verdict_line_format():
    line = doctor_verdict_line()
    assert line.startswith("VERDICT:")
    assert any(x in line for x in ("READY", "BLOCKED", "DEGRADED", "ERROR"))

def test_full_text_ends_with_verdict():
    text = doctor_full_text(include_board=False)
    assert "VERDICT:" in text

def test_run_doctor_critical_attr():
    r = run_doctor()
    assert hasattr(r, "critical_ok")
