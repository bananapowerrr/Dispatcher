# -*- coding: utf-8 -*-
"""Список проектов из PROJECT_* (.env / config)."""
from __future__ import annotations

import customtkinter as ctk

from ui.paths import ensure_sys_path
from ui.i18n_ui import t as _t


class ProjectsPanel(ctk.CTkFrame):
    def __init__(self, parent, on_select=None):
        super().__init__(parent)
        self.on_select = on_select
        self._selected = ""

        ctk.CTkLabel(self, text=_t("projects_title", default="Проекты"), font=ctk.CTkFont(size=14, weight="bold")).pack(
            anchor="w", padx=10, pady=(10, 4)
        )
        self.listbox = ctk.CTkScrollableFrame(self)
        self.listbox.pack(fill="both", expand=True, padx=8, pady=8)

        self.channel_var = ctk.StringVar(value="gpt")
        ch_frame = ctk.CTkFrame(self)
        ch_frame.pack(fill="x", padx=8, pady=8)
        ctk.CTkLabel(ch_frame, text=_t("channel_label", default="Канал:")).pack(side="left")
        self.channel_menu = ctk.CTkOptionMenu(
            ch_frame, variable=self.channel_var, values=["gpt", "grok", "gemini", "autopilot"]
        )
        self.channel_menu.pack(side="left", padx=8)

        ctk.CTkButton(self, text=_t("refresh", default="Обновить"), command=self.reload).pack(fill="x", padx=8, pady=(0, 10))
        self.reload()

    @property
    def selected_project(self) -> str:
        return self._selected

    @property
    def selected_channel(self) -> str:
        return self.channel_var.get()

    def reload(self) -> None:
        for w in self.listbox.winfo_children():
            w.destroy()
        ensure_sys_path()
        try:
            from config import list_projects
            projects = list_projects()
        except Exception as exc:
            ctk.CTkLabel(self.listbox, text=f"Ошибка: {exc}").pack(anchor="w")
            return
        # unique by path
        seen = set()
        names = []
        for name, path in projects.items():
            key = str(path)
            if key in seen:
                continue
            # skip pure alias lower duplicates preference for dashed names
            if name != name.lower() and name.lower() in projects:
                display = name
            elif "-" in name or name[0].isupper():
                display = name
            else:
                continue
            seen.add(key)
            names.append((display, path))
        if not names:
            ctk.CTkLabel(self.listbox, text="Нет PROJECT_* в .env").pack(anchor="w")
            return
        for name, path in sorted(names, key=lambda x: x[0].lower()):
            btn = ctk.CTkButton(
                self.listbox,
                text=f"📁 {name}",
                anchor="w",
                fg_color="transparent",
                command=lambda n=name: self._pick(n),
            )
            btn.pack(fill="x", pady=2)
            ctk.CTkLabel(self.listbox, text=str(path)[:60], text_color="gray", anchor="w").pack(
                fill="x", padx=12
            )

    def _pick(self, name: str) -> None:
        self._selected = name
        if self.on_select:
            self.on_select(name)
