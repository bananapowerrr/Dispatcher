# -*- coding: utf-8 -*-
"""FC-45 Progressive workspace modes for NVCode UI.

Modes are visibility profiles over existing panels — not separate apps.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# Panel keys used by main_window visibility map
PANEL_EXPLORER = "explorer"
PANEL_EDITOR = "editor"
PANEL_CHAT = "chat"
PANEL_QUEUE = "queue"
PANEL_TASK = "task_detail"
PANEL_CHANGES = "changes"
PANEL_DIFF = "diff"
PANEL_PROJECT = "project_center"
PANEL_LOGS = "logs"
PANEL_HISTORY = "history"
PANEL_METRICS = "metrics"
PANEL_WORKERS = "workers"
PANEL_SKILLS = "skills"
PANEL_RECIPES = "recipes"
PANEL_PEV = "pev"
PANEL_SENTINEL = "sentinel"
PANEL_PHONE = "phone"
PANEL_EXTENSIONS = "extensions"


@dataclass
class WorkspaceMode:
    """Named visibility profile."""

    id: str
    label: str
    description: str
    # right-side tab names to show (others can stay registered but hidden if toolkit allows)
    right_tabs: list[str] = field(default_factory=list)
    show_explorer: bool = True
    show_editor: bool = True
    show_chat: bool = True
    default_right_tab: str = "Логи"


MODES: dict[str, WorkspaceMode] = {
    "code": WorkspaceMode(
        id="code",
        label="Code",
        description="Explorer + Editor + Changes/Diff",
        right_tabs=["Changes", "Diff", "Логи", "История", "Problems"],
        show_explorer=True,
        show_editor=True,
        show_chat=False,
        default_right_tab="Changes",
    ),
    "agent": WorkspaceMode(
        id="agent",
        label="Agent",
        description="Chat + Queue + Task + Diff",
        right_tabs=["Очередь", "Task", "Diff", "Логи", "История", "Решения"],
        show_explorer=True,
        show_editor=True,
        show_chat=True,
        default_right_tab="Очередь",
    ),
    "project": WorkspaceMode(
        id="project",
        label="Project",
        description="Project Center + Audit/Plan focus",
        right_tabs=["Проект", "Очередь", "История", "Логи"],
        show_explorer=True,
        show_editor=False,
        show_chat=True,
        default_right_tab="Проект",
    ),
    "full": WorkspaceMode(
        id="full",
        label="Full",
        description="All panels (advanced)",
        right_tabs=[],  # empty = show all
        show_explorer=True,
        show_editor=True,
        show_chat=True,
        default_right_tab="Логи",
    ),
}


def list_modes() -> list[dict[str, str]]:
    return [
        {"id": m.id, "label": m.label, "description": m.description}
        for m in MODES.values()
    ]


def get_mode(mode_id: str) -> WorkspaceMode:
    return MODES.get((mode_id or "").lower()) or MODES["agent"]


def resolve_beginner_mode() -> str:
    """Default progressive disclosure entry for new users."""
    return "agent"


def should_show_panel(mode_id: str, panel_key: str) -> bool:
    m = get_mode(mode_id)
    if m.id == "full":
        return True
    if panel_key == PANEL_EXPLORER:
        return m.show_explorer
    if panel_key == PANEL_EDITOR:
        return m.show_editor
    if panel_key == PANEL_CHAT:
        return m.show_chat
    # right tabs controlled separately
    return True


def tab_allowed(mode_id: str, tab_name: str) -> bool:
    m = get_mode(mode_id)
    if not m.right_tabs:
        return True
    # fuzzy: allow if name matches any allowed (ru/en variants)
    allowed = {t.lower() for t in m.right_tabs}
    n = (tab_name or "").lower()
    if n in allowed:
        return True
    # aliases
    aliases = {
        "logs": "логи",
        "history": "история",
        "queue": "очередь",
        "project": "проект",
        "task": "task",
        "changes": "changes",
        "diff": "diff",
    }
    if aliases.get(n) in allowed or n in {a for a in aliases.values()}:
        return True
    for a in m.right_tabs:
        if a.lower() in n or n in a.lower():
            return True
    return False
