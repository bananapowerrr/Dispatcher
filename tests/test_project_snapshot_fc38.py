# -*- coding: utf-8 -*-
"""FC-38A/B Project Snapshot + Audit tests."""
from __future__ import annotations

from pathlib import Path

from intelligence.project_audit import run_project_audit
from intelligence.project_snapshot import build_project_snapshot


def test_snapshot_minimal(tmp_path: Path):
    (tmp_path / "a.py").write_text("x=1\n", encoding="utf-8")
    snap = build_project_snapshot(tmp_path, include_capabilities=False)
    assert snap.project_name == tmp_path.name
    assert snap.status in ("ready", "empty", "needs_decision", "blocked", "executing", "unknown")
    text = snap.format_human()
    assert "Project" in text or snap.project_name in text
    d = snap.to_dict()
    assert "sections" in d


def test_audit_with_tests(tmp_path: Path):
    (tmp_path / "README.md").write_text("# hi\n", encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_x.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    (tmp_path / "m.py").write_text("x=1\n", encoding="utf-8")
    rep = run_project_audit(tmp_path)
    assert rep.areas
    assert any(a.name == "Testing" for a in rep.areas)
    text = rep.format_human()
    assert "AUDIT" in text
    assert "Analysis" in text or "Audit" in text or "≠" in text


def test_audit_findings_sorted(tmp_path: Path):
    (tmp_path / "x.py").write_text("eval('1')\n", encoding="utf-8")
    rep = run_project_audit(tmp_path)
    if len(rep.findings) >= 2:
        order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
        scores = [order.get(f.severity, 9) for f in rep.findings]
        assert scores == sorted(scores)
