# -*- coding: utf-8 -*-
"""FC-07: last_outcome helpers for workers/skills panels."""
from __future__ import annotations

import json
from pathlib import Path


def test_last_task_result_from_done(tmp_path: Path):
    from ui.last_outcome import last_task_result, format_worker_line

    done = tmp_path / "channels" / "desktop" / "done"
    done.mkdir(parents=True)
    row = {
        "id": "t-abc123",
        "status": "DONE",
        "result": {
            "ok": True,
            "worker": "aider_local",
            "summary": "updated readme",
            "latency": 12.5,
            "files_changed": ["README.md"],
            "verification": {"passed": True, "summary": "Verify PASS (1/1)"},
        },
    }
    (done / "t-abc123.json").write_text(json.dumps(row), encoding="utf-8")
    tr = last_task_result(tmp_path)
    assert tr is not None
    assert tr.get("ok") is True
    assert "aider" in (tr.get("worker") or "")
    line = format_worker_line(tr)
    assert "✓" in line or "DONE" in line


def test_last_outcomes_by_worker(tmp_path: Path):
    from ui.last_outcome import last_outcomes_by_worker

    done = tmp_path / "channels" / "gpt" / "done"
    done.mkdir(parents=True)
    (done / "a.json").write_text(
        json.dumps(
            {
                "id": "a",
                "status": "DONE",
                "result": {"ok": True, "worker": "ollama", "summary": "ok"},
            }
        ),
        encoding="utf-8",
    )
    by = last_outcomes_by_worker(tmp_path)
    assert "ollama" in by
