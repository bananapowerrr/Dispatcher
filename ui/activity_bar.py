# -*- coding: utf-8 -*-
"""P4 Activity Bar — narrow left strip to switch primary views (VS Code-like)."""
from __future__ import annotations

from typing import Any, Callable

try:
    import customtkinter as ctk
except ImportError:  # pragma: no cover
    ctk = None  # type: ignore

# id → (icon, tooltip/label)
DEFAULT_ITEMS = (
    ("explorer", "📁", "Explorer"),
    ("search", "🔎", "Search"),
    ("plan", "📋", "Plan"),
    ("agent", "🤖", "Agent / Chat"),
    ("problems", "⚠", "Problems"),
    ("git", "⑂", "Changes"),
    ("extensions", "🧩", "Extensions"),
    ("settings", "⚙", "Settings"),
)


class ActivityBar(ctk.CTkFrame if ctk else object):  # type: ignore
    def __init__(
        self,
        master,
        *,
        on_select: Callable[[str], None] | None = None,
        items: tuple = DEFAULT_ITEMS,
        **kwargs: Any,
    ):
        if ctk is None:
            raise RuntimeError("customtkinter required")
        super().__init__(master, width=48, **kwargs)
        self.pack_propagate(False)
        self._on_select = on_select
        self._active = ""
        self._buttons: dict[str, Any] = {}
        for vid, icon, _label in items:
            btn = ctk.CTkButton(
                self,
                text=icon,
                width=40,
                height=40,
                fg_color="transparent",
                command=lambda i=vid: self.select(i),
            )
            btn.pack(pady=4, padx=4)
            self._buttons[vid] = btn
        # spacer + settings at bottom feel: already in list

    def select(self, view_id: str) -> None:
        self._active = view_id
        for vid, btn in self._buttons.items():
            try:
                btn.configure(fg_color=("#3a7ebf" if vid == view_id else "transparent"))
            except Exception:
                pass
        if self._on_select:
            try:
                self._on_select(view_id)
            except Exception:
                pass
