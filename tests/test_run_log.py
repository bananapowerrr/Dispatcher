"""RunSession offline diagnostics."""
from __future__ import annotations

from pathlib import Path

from utils.run_log import RunSession, make_run_id, render_summary_md, latest_run_dir


def test_make_run_id_shape():
    rid = make_run_id()
    assert "_" in rid
    assert len(rid) > 15


def test_session_writes_artifacts(tmp_path: Path):
    sess = RunSession(tmp_path, meta={"kind": "test"})
    sess.event("TASK_CREATED", task_id="t1")
    sess.event("VERIFY_PASSED")
    summary = sess.finish(
        final_status="DONE",
        task="add helper",
        worker="mock",
        duration_sec=1.2,
        files_changed=["a.py"],
        verification={"passed": True},
        events=["TASK_CREATED", "VERIFY_PASSED", "TASK_DONE"],
    )
    assert summary.is_file()
    assert (sess.dir / "result.json").is_file()
    assert (sess.dir / "events.jsonl").is_file()
    text = summary.read_text(encoding="utf-8")
    assert "DONE" in text
    assert "add helper" in text
    assert latest_run_dir(tmp_path) == sess.dir


def test_render_summary_fail():
    md = render_summary_md(
        {
            "run_id": "r1",
            "final_status": "ERROR",
            "task": "broken",
            "events": ["VERIFY_FAILED"],
            "error": "boom",
            "verification": {"passed": False},
        }
    )
    assert "ERROR" in md
    assert "VERIFY_FAILED" in md
