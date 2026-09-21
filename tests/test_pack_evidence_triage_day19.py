# -*- coding: utf-8 -*-
"""Day 19: pack_run_evidence includes triage section."""
from __future__ import annotations

import json
from pathlib import Path

import pytest


def test_pack_includes_triage(tmp_path: Path):
    # load pack from artifacts or repo
    import importlib.util
    candidates = [
        Path(__file__).resolve().parents[1] / "scripts" / "pack_run_evidence.py",
        Path("/home/workdir/artifacts/scripts/pack_run_evidence.py"),
    ]
    path = next(p for p in candidates if p.is_file())
    spec = importlib.util.spec_from_file_location("pack_run_evidence", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(mod)

    run = tmp_path / "run1"
    run.mkdir()
    (run / "result.json").write_text(
        json.dumps(
            {
                "status": "error",
                "result": {"error": "verification failed: syntax error", "worker": "aider_local"},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (run / "summary.md").write_text("# sum\n", encoding="utf-8")
    text = mod.pack(run)
    assert "## triage" in text
    assert "FAIL LAYER" in text
    assert "VERIFY" in text


def test_pack_no_result_still_ok(tmp_path: Path):
    import importlib.util

    path = Path("/home/workdir/artifacts/scripts/pack_run_evidence.py")
    if not path.is_file():
        path = Path(__file__).resolve().parents[1] / "scripts" / "pack_run_evidence.py"
    spec = importlib.util.spec_from_file_location("pack_run_evidence", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(mod)
    run = tmp_path / "run2"
    run.mkdir()
    (run / "summary.md").write_text("ok\n", encoding="utf-8")
    text = mod.pack(run)
    assert "Evidence pack" in text
