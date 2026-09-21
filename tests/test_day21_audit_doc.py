from pathlib import Path

def test_day21_audit_has_p0_and_chain():
    paths = [
        Path("/home/workdir/artifacts/docs/DAY21_PRODUCT_READINESS_AUDIT.md"),
        Path(__file__).resolve().parents[1] / "docs" / "DAY21_PRODUCT_READINESS_AUDIT.md",
    ]
    p = next(x for x in paths if x.is_file())
    text = p.read_text(encoding="utf-8")
    assert "P0-1" in text and "P0-2" in text
    assert "select_executor" in text
    assert "chat_recovery_bridge" in text
    assert "LIVE-001" in text
    assert "settings_panel" in text
