"""Changes/queue empty offline."""
from __future__ import annotations

from ui.changes_hints import changes_empty_text
from app.facade import AppFacade


def test_changes_no_project():
    t = changes_empty_text(has_project=False)
    assert "проект" in t.lower() or "Setup" in t


def test_changes_with_project():
    t = changes_empty_text(has_project=True)
    assert "Apply" in t or "Review" in t or "git" in t.lower()


def test_facade_queue():
    msg = AppFacade().empty_message("queue")
    assert "Очеред" in msg or "queue" in msg.lower() or "пуст" in msg.lower()
