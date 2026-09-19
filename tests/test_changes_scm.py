"""ChangesService SCM helpers (offline, no real git required if fail soft)."""
from __future__ import annotations

from pathlib import Path

from app.changes_service import ChangesService


def test_count_changes_on_tmp(tmp_path: Path):
    # non-git dir → empty list / 0
    svc = ChangesService(str(tmp_path))
    assert svc.count_changes() == 0
    assert svc.list_changes() == []


def test_stage_path_outside_rejected(tmp_path: Path):
    svc = ChangesService(str(tmp_path))
    ok, msg = svc.stage_path("../etc/passwd")
    assert ok is False
    assert "outside" in msg.lower() or "path" in msg.lower() or "no" in msg.lower()


def test_discard_empty_path(tmp_path: Path):
    svc = ChangesService(str(tmp_path))
    ok, msg = svc.discard_path("")
    assert ok is False


def test_format_footer_git_n():
    from ui.status_labels import format_footer
    s = format_footer(dispatcher_on=True, queue_n=0, git_n=3)
    assert "git:3" in s
