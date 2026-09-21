# -*- coding: utf-8 -*-
"""Day 17: live001_preflight script is import-safe and matrix has Day 13–16 rows."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_preflight_script_exists_and_parses():
    p = ROOT / "scripts" / "live001_preflight.py"
    if not p.is_file():
        p = Path("/home/workdir/artifacts/scripts/live001_preflight.py")
    src = p.read_text(encoding="utf-8")
    compile(src, str(p), "exec")
    assert "LIVE-001" in src
    assert "worker_route_surface" in src
    assert "settings_contract" in src


def test_matrix_has_day13_16_rows():
    p = ROOT / "scripts" / "offline_acceptance_matrix.py"
    if not p.is_file():
        p = Path("/home/workdir/artifacts/scripts/offline_acceptance_matrix.py")
    src = p.read_text(encoding="utf-8")
    for key in (
        "day13_settings_contract",
        "day13_1_settings_ro_enforced",
        "day14_recovery_chat",
        "day15_context_report",
        "day16_worker_route_surface",
    ):
        assert key in src, key


def test_ci_offline_mentions_preflight():
    p = ROOT / "scripts" / "ci_offline.sh"
    if not p.is_file():
        p = Path("/home/workdir/artifacts/scripts/ci_offline.sh")
    src = p.read_text(encoding="utf-8")
    assert "live001_preflight" in src
    assert "day13" in src or "Day 13" in src or "day-surface" in src
