# -*- coding: utf-8 -*-
"""Modern dark theme tokens for AgentBus UI (Cursor/Claude-like)."""
from __future__ import annotations

# Palette
BG = "#0f1115"
BG_PANEL = "#161a22"
BG_ELEVATED = "#1c2230"
BORDER = "#2a3344"
TEXT = "#e8eaed"
TEXT_DIM = "#9aa3b2"
ACCENT = "#5b8def"
ACCENT_SOFT = "#3d5a80"
SUCCESS = "#3dd68c"
WARN = "#f0b429"
DANGER = "#f07178"
INFO = "#7dcfff"

KIND_COLORS = {
    "thinking": "#a78bfa",
    "tool": "#38bdf8",
    "pulse": "#fbbf24",
    "done": SUCCESS,
    "error": DANGER,
    "plan": "#34d399",
    "system": TEXT_DIM,
}


def apply_appearance() -> None:
    """Global CTk appearance — safe to call at startup."""
    try:
        import customtkinter as ctk
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("dark-blue")
    except Exception:
        pass


def kind_badge(kind: str) -> str:
    k = (kind or "").lower()
    if k in ("", "other"):
        return ""
    try:
        from language_guard import format_stream_badge
        return format_stream_badge(k)
    except Exception:
        mapping = {
            "thinking": "THINKING",
            "tool": "TOOL_CALL",
            "tool_call": "TOOL_CALL",
            "pulse": "PULSE",
            "done": "DONE",
            "error": "ERROR",
            "plan": "PLAN",
            "loop": "LOOP",
        }
        return mapping.get(k, k.upper())
