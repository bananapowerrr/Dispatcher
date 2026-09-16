# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path


def test_stage_verify_policy_injects():
    from core.pipeline_stages import stage_pre_enrich

    raw = {
        "id": "t1",
        "message": "refactor module",
        "files": ["a.py"],
        "verify": [],
        "metadata": {"complexity": 4},
    }
    out = stage_pre_enrich(raw)
    assert out.get("verify")
    assert int(out["metadata"].get("verify_ladder") or 0) >= 2


def test_stage_attachments_text(tmp_path, monkeypatch):
    from core.pipeline_stages import stage_attachments

    src = tmp_path / "note.txt"
    src.write_text("hello pipeline", encoding="utf-8")
    # point BUS_ROOT via env if config supports - use materialize path through enrich
    raw = {
        "id": "att1",
        "message": "use file",
        "metadata": {"attachment_paths": [str(src)]},
    }
    # enrich needs BUS_ROOT - may use default; ensure doesn't crash
    out = stage_attachments(raw)
    assert "message" in out


def test_record_verify_ladder_metrics():
    from utils.metrics import MetricsCollector

    m = MetricsCollector()
    m.record_verify_ladder(success=False, level=2)
    m.record_verify_ladder(success=False, level=2)
    m.record_verify_ladder(success=True, level=3)
    assert m.counters["verify_ladder_fail"] == 2
    assert m.counters["verify_ladder_fail_L2"] == 2
    assert m.counters["verify_ladder_pass"] == 1


def test_process_body_is_thin():
    """Guard: _process_body lives in rp_lifecycle after runtime split."""
    from pathlib import Path
    import re as _re
    src = Path("src/core/rp_lifecycle.py")
    assert src.is_file(), "rp_lifecycle.py missing"
    content = src.read_text(encoding="utf-8")
    m = _re.search(
        r"def _process_body\(self, raw: dict\).*?(?=\n    def |\nclass |\Z)",
        content,
        _re.S,
    )
    assert m, "_process_body not found in rp_lifecycle"
    body = m.group(0)
    lines = [ln for ln in body.splitlines() if ln.strip() and not ln.strip().startswith("#")]
    assert len(lines) < 400, f"_process_body still too large: {len(lines)} lines"
