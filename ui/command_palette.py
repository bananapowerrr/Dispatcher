# -*- coding: utf-8 -*-
"""Ctrl+K command palette."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import customtkinter as ctk


@dataclass
class Command:
    id: str
    title: str
    category: str
    shortcut: str | None
    action: Callable[[], None]
    keywords: list[str] = field(default_factory=list)


class CommandPalette:
    """Fuzzy-ish filterable command launcher."""

    def __init__(self, root: ctk.CTk, commands: list[Command]) -> None:
        self.root = root
        self.commands = commands
        self.window: ctk.CTkToplevel | None = None
        self.selected_index = 0
        self.filtered: list[Command] = list(commands)

    def open(self) -> None:
        if self.window is not None:
            try:
                if self.window.winfo_exists():
                    self.window.destroy()
            except Exception:
                pass
        self.window = ctk.CTkToplevel(self.root)
        self.window.title("Палитра команд")
        self.window.geometry("620x480")
        self.window.attributes("-topmost", True)
        try:
            self.window.update_idletasks()
            x = self.root.winfo_x() + max(0, (self.root.winfo_width() - 620) // 2)
            y = self.root.winfo_y() + 80
            self.window.geometry(f"+{x}+{y}")
        except Exception:
            pass

        self.search = ctk.CTkEntry(self.window, placeholder_text="Найти команду… (например: диспетчер, рецепт, тема)", height=36)
        self.search.pack(fill="x", padx=16, pady=(16, 8))
        self.search.bind("<KeyRelease>", self._on_search)
        self.search.bind("<Return>", self._execute_selected)
        self.search.bind("<Escape>", lambda e: self.close())
        self.search.bind("<Down>", lambda e: self._move(1))
        self.search.bind("<Up>", lambda e: self._move(-1))

        self.list_frame = ctk.CTkScrollableFrame(self.window)
        self.list_frame.pack(fill="both", expand=True, padx=16, pady=8)
        self.filtered = list(self.commands)
        self.selected_index = 0
        self._render()
        self.search.focus_force()

    def close(self) -> None:
        if self.window is not None:
            try:
                self.window.destroy()
            except Exception:
                pass
            self.window = None

    def _on_search(self, _event=None) -> None:
        q = (self.search.get() or "").lower().strip()
        if not q:
            self.filtered = list(self.commands)
        else:
            self.filtered = [
                c
                for c in self.commands
                if q in c.title.lower()
                or q in c.category.lower()
                or any(q in kw.lower() for kw in c.keywords)
            ]
        self.selected_index = 0
        self._render()

    def _render(self) -> None:
        for w in self.list_frame.winfo_children():
            w.destroy()
        for i, cmd in enumerate(self.filtered[:25]):
            bg = ("gray75", "gray30") if i == self.selected_index else "transparent"
            row = ctk.CTkFrame(self.list_frame, fg_color=bg, corner_radius=4)
            row.pack(fill="x", pady=2)
            ctk.CTkLabel(row, text=cmd.title, anchor="w").pack(side="left", padx=10, pady=6)
            if cmd.shortcut:
                ctk.CTkLabel(row, text=cmd.shortcut, text_color="gray").pack(side="right", padx=8)
            ctk.CTkLabel(row, text=cmd.category, text_color="gray").pack(side="right", padx=8)
            row.bind("<Button-1>", lambda e, c=cmd: self._execute(c))

    def _move(self, delta: int) -> None:
        if not self.filtered:
            return
        self.selected_index = max(0, min(len(self.filtered) - 1, self.selected_index + delta))
        self._render()

    def _execute_selected(self, _event=None) -> None:
        if self.filtered:
            self._execute(self.filtered[self.selected_index])

    def _execute(self, command: Command) -> None:
        self.close()
        try:
            command.action()
        except Exception:
            pass
