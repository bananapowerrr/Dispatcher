# -*- coding: utf-8 -*-
"""Unified ? help popover for NVCode (FC-45).

Usage:
    HelpPopover.show(parent, title="Почему?", body="...", anchor_widget=btn)
Click outside or Escape closes.
"""
from __future__ import annotations

from typing import Any

try:
    import customtkinter as ctk
except ImportError:  # pragma: no cover
    ctk = None  # type: ignore


class HelpPopover:
    """Small top-level explanation bubble — one component for whole UI."""

    _current: Any = None

    @classmethod
    def close(cls) -> None:
        w = cls._current
        cls._current = None
        if w is not None:
            try:
                w.destroy()
            except Exception:
                pass

    @classmethod
    def show(
        cls,
        parent: Any,
        *,
        title: str = "Почему?",
        body: str = "",
        anchor_widget: Any = None,
        width: int = 320,
    ) -> None:
        if ctk is None:
            return
        cls.close()
        win = ctk.CTkToplevel(parent)
        cls._current = win
        win.title("")
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        frame = ctk.CTkFrame(win, corner_radius=8, border_width=1)
        frame.pack(fill="both", expand=True, padx=1, pady=1)
        ctk.CTkLabel(frame, text=title, font=ctk.CTkFont(weight="bold")).pack(
            anchor="w", padx=12, pady=(10, 4)
        )
        box = ctk.CTkTextbox(frame, width=width, height=min(180, 40 + 14 * max(3, body.count("\n") + 2)), wrap="word")
        box.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        box.insert("1.0", body or "—")
        box.configure(state="disabled")
        try:
            win.update_idletasks()
            if anchor_widget is not None:
                x = anchor_widget.winfo_rootx()
                y = anchor_widget.winfo_rooty() + anchor_widget.winfo_height() + 4
            else:
                x = parent.winfo_rootx() + 40
                y = parent.winfo_rooty() + 80
            win.geometry(f"+{x}+{y}")
        except Exception:
            pass
        win.bind("<Escape>", lambda e: cls.close())
        # click outside: bind to parent root
        try:
            root = parent.winfo_toplevel()
            root.bind("<Button-1>", lambda e: cls.close(), add="+")
        except Exception:
            pass


def why_button(parent: Any, *, title: str, body: str, **kwargs: Any) -> Any:
    """Create a small [?] button that opens HelpPopover."""
    if ctk is None:
        return None

    def _open() -> None:
        HelpPopover.show(parent, title=title, body=body, anchor_widget=btn)

    btn = ctk.CTkButton(parent, text="?", width=28, height=24, command=_open, **kwargs)
    return btn
