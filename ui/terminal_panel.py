# -*- coding: utf-8 -*-
"""P4 Terminal stub — scrollable process/output log (not a full PTY yet)."""
from __future__ import annotations

import time
from typing import Any

try:
    import customtkinter as ctk
except ImportError:  # pragma: no cover
    ctk = None  # type: ignore


def format_term_line(source: str, message: str, *, ts: str | None = None) -> str:
    """Format one terminal log line: '[HH:MM:SS] source: message\\n'."""
    stamp = ts or time.strftime("%H:%M:%S")
    who = source or "system"
    return f"[{stamp}] {who}: {message}\n"


class TerminalPanel(ctk.CTkFrame if ctk else object):  # type: ignore
    def __init__(self, master, **kwargs: Any):
        if ctk is None:
            raise RuntimeError("customtkinter required")
        super().__init__(master, **kwargs)
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=4, pady=2)
        ctk.CTkLabel(top, text="Output", font=ctk.CTkFont(size=12, weight="bold")).pack(side="left")
        ctk.CTkButton(top, text="Clear", width=56, command=self.clear).pack(side="right", padx=2)
        self._text = ctk.CTkTextbox(self, height=120, font=ctk.CTkFont(family="Consolas", size=12))
        self._text.pack(fill="both", expand=True, padx=4, pady=4)
        self.append("system", "Terminal stub ready — logs from Run / dispatcher appear here.")

    def focus(self) -> None:
        try:
            for attr in ("_text", "text", "_box"):
                w = getattr(self, attr, None)
                if w is not None and hasattr(w, "focus_set"):
                    w.focus_set()
                    return
        except Exception:
            pass

    def clear(self) -> None:

        try:
            self._text.delete("1.0", "end")
        except Exception:
            pass

    def append(self, source: str, message: str) -> None:
        line = format_term_line(source, message)
        try:
            self._text.insert("end", line)
            self._text.see("end")
        except Exception:
            pass

    def refresh(self) -> None:
        """No-op for F5 compatibility."""
        pass
