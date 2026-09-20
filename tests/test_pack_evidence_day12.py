# -*- coding: utf-8 -*-
"""Day-12 offline: pack_run_evidence triage section."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

# import pack helpers
import importlib.util

_spec = importlib.util.spec_from_file_location(
    "pack_run_evidence",
    ROOT / "scripts" / "pack_run_evidence.py",
)
_mod = importlib.util.module_from_spec(_spec)
assert _spec and _spec.loader
_spec.loader.exec_module(_mod)


def test_pack_includes_triage_class(tmp_path: Path):
    run = tmp_path / "run1"
    run.mkdir()
    (run / "result.json").write_text(
        json.dumps(
            {
                "status": "ERROR",
                "worker": "aider_local",
                "error": "Connection refused to ollama",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    text = _mod.pack(run)
    assert "## triage" in text
    assert "class:" in text
    # offline/connection pattern should classify
    assert "offline" in text or "hint:" in text or "ollama" in text.lower()


def test_pack_empty_run_still_valid(tmp_path: Path):
    run = tmp_path / "empty"
    run.mkdir()
    text = _mod.pack(run)
    assert "Evidence pack" in text
