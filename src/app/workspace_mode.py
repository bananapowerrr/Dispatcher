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


def panel_visibility(mode_id: str) -> dict[str, bool]:
    """FC-45G: full panel → visible map for progressive workspace."""
    m = get_mode(mode_id)
    if m.id == "full":
        return {
            PANEL_EXPLORER: True,
            PANEL_EDITOR: True,
            PANEL_CHAT: True,
            PANEL_QUEUE: True,
            PANEL_TASK: True,
            PANEL_CHANGES: True,
            PANEL_DIFF: True,
            PANEL_PROJECT: True,
            PANEL_LOGS: True,
            PANEL_HISTORY: True,
            PANEL_METRICS: True,
            PANEL_WORKERS: True,
            PANEL_SKILLS: True,
            PANEL_RECIPES: True,
            PANEL_PEV: True,
            PANEL_SENTINEL: True,
            PANEL_PHONE: True,
            PANEL_EXTENSIONS: True,
        }
    # base from mode flags
    vis = {
        PANEL_EXPLORER: m.show_explorer,
        PANEL_EDITOR: m.show_editor,
        PANEL_CHAT: m.show_chat,
        PANEL_QUEUE: tab_allowed(mode_id, "Queue") or tab_allowed(mode_id, "Очередь"),
        PANEL_TASK: tab_allowed(mode_id, "Task") or m.id == "agent",
        PANEL_CHANGES: tab_allowed(mode_id, "Changes"),
        PANEL_DIFF: tab_allowed(mode_id, "Diff"),
        PANEL_PROJECT: tab_allowed(mode_id, "Project") or tab_allowed(mode_id, "Проект"),
        PANEL_LOGS: tab_allowed(mode_id, "Логи") or tab_allowed(mode_id, "Logs"),
        PANEL_HISTORY: tab_allowed(mode_id, "История") or tab_allowed(mode_id, "History"),
        PANEL_METRICS: m.id in ("full", "project"),
        PANEL_WORKERS: m.id in ("full", "agent"),
        PANEL_SKILLS: m.id == "full",
        PANEL_RECIPES: m.id == "full",
        PANEL_PEV: m.id == "full",
        PANEL_SENTINEL: m.id == "full",
        PANEL_PHONE: m.id == "full",
        PANEL_EXTENSIONS: m.id == "full",
    }
    if m.id == "code":
        vis[PANEL_CHAT] = False
        vis[PANEL_QUEUE] = False
        vis[PANEL_CHANGES] = True
        vis[PANEL_DIFF] = True
    elif m.id == "agent":
        vis[PANEL_CHAT] = True
        vis[PANEL_QUEUE] = True
        vis[PANEL_TASK] = True
        vis[PANEL_DIFF] = True
    elif m.id == "project":
        vis[PANEL_PROJECT] = True
        vis[PANEL_HISTORY] = True
        vis[PANEL_CHAT] = True
    return vis


def format_mode_help(mode_id: str = "") -> str:
    """Human blurb for current progressive mode."""
    m = get_mode(mode_id or resolve_beginner_mode())
    vis = panel_visibility(m.id)
    on = [k for k, v in vis.items() if v]
    return f"Mode {m.label}: {m.description}\nPanels: {', '.join(on[:12])}"

