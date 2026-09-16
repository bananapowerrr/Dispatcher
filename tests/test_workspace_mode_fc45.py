# -*- coding: utf-8 -*-
from __future__ import annotations

from app.nav_history import NavContext, NavHistory
from app.workspace_mode import (
    get_mode,
    list_modes,
    resolve_beginner_mode,
    should_show_panel,
    tab_allowed,
)


def test_modes_exist():
    ids = {m["id"] for m in list_modes()}
    assert {"code", "agent", "project", "full"} <= ids


def test_beginner_is_agent():
    assert resolve_beginner_mode() == "agent"


def test_code_hides_chat():
    assert should_show_panel("code", "chat") is False
    assert should_show_panel("code", "editor") is True


def test_agent_shows_chat():
    assert should_show_panel("agent", "chat") is True


def test_full_shows_all():
    assert should_show_panel("full", "chat") is True
    assert tab_allowed("full", "anything") is True


def test_tab_allowed_queue_agent():
    assert tab_allowed("agent", "Очередь") is True
    assert tab_allowed("project", "Проект") is True


def test_nav_history_back_forward():
    h = NavHistory()
    h.push(NavContext(kind="project", project="/a", label="A"))
    h.push(NavContext(kind="file", project="/a", file="x.py", label="x"))
    h.push(NavContext(kind="task", task_id="t1", label="task"))
    assert h.can_back()
    cur = h.back()
    assert cur and cur.file == "x.py"
    cur = h.back()
    assert cur and cur.kind == "project"
    assert not h.can_back()
    assert h.can_forward()
    cur = h.forward()
    assert cur and cur.file == "x.py"


def test_nav_skips_duplicate():
    h = NavHistory()
    h.push({"kind": "file", "file": "a.py"})
    h.push({"kind": "file", "file": "a.py"})
    assert len(h.snapshot()["items"]) == 1
