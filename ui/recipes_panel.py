# -*- coding: utf-8 -*-
"""Рецепты — быстрые сценарии задач из recipes/*.json."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import customtkinter as ctk

from ui.i18n_ui import t as _t


class RecipesPanel(ctk.CTkFrame):
    """Список рецептов + запуск в desktop-очередь."""

    def __init__(
        self,
        master,
        *,
        on_enqueue: Callable[[dict[str, Any]], None] | None = None,
        get_project: Callable[[], str] | None = None,
        **kwargs,
    ):
        super().__init__(master, **kwargs)
        self.on_enqueue = on_enqueue
        self.get_project = get_project
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        ctk.CTkLabel(
            self,
            text=_t("recipes_title", default="Рецепты"),
            font=ctk.CTkFont(size=16, weight="bold"),
        ).grid(row=0, column=0, sticky="w", padx=12, pady=(12, 4))

        ctk.CTkLabel(
            self,
            text=_t("recipes_hint", default="Готовые сценарии → задача в очередь чата"),
            text_color="gray",
        ).grid(row=1, column=0, sticky="w", padx=12, pady=(0, 8))

        self._list = ctk.CTkScrollableFrame(self)
        self._list.grid(row=2, column=0, sticky="nsew", padx=8, pady=8)
        self._list.grid_columnconfigure(0, weight=1)

        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.grid(row=3, column=0, sticky="ew", padx=12, pady=8)
        ctk.CTkButton(bar, text=_t("recipes_refresh", default="Обновить"), width=100, command=self.refresh).pack(side="left")
        self._status = ctk.CTkLabel(bar, text="")
        self._status.pack(side="left", padx=12)

        self.refresh()

    def refresh(self) -> None:
        for w in self._list.winfo_children():
            w.destroy()
        try:
            from cli.recipes import list_recipes
            items = list_recipes()
        except Exception as exp:
            ctk.CTkLabel(self._list, text=f"Ошибка: {exp}").grid(row=0, column=0, sticky="w")
            return
        if not items:
            ctk.CTkLabel(
                self._list,
                text=_t("recipes_empty", default="Нет recipes/*.json — положите шаблоны в recipes/"),
            ).grid(row=0, column=0, sticky="w", padx=8, pady=8)
            return
        for i, rec in enumerate(items):
            self._row(i, rec)
        self._status.configure(text=f"{len(items)} рецептов")

    def _row(self, idx: int, rec: dict[str, Any]) -> None:
        meta = rec.get("metadata") if isinstance(rec.get("metadata"), dict) else {}
        rid = str(meta.get("recipe") or Path(str(rec.get("_path") or "")).stem or rec.get("id") or idx)
        title = str(rec.get("title") or rid)
        msg = str(rec.get("message") or "")[:160]
        frame = ctk.CTkFrame(self._list)
        frame.grid(row=idx, column=0, sticky="ew", padx=4, pady=4)
        frame.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(frame, text=title, font=ctk.CTkFont(weight="bold"), anchor="w").grid(
            row=0, column=0, sticky="w", padx=8, pady=(6, 0)
        )
        ctk.CTkLabel(frame, text=msg, anchor="w", justify="left", wraplength=420).grid(
            row=1, column=0, sticky="w", padx=8, pady=(2, 6)
        )
        ctk.CTkButton(
            frame,
            text=_t("recipes_run", default="Запустить"),
            width=100,
            command=lambda r=rid, m=msg, files=list(rec.get("files") or []): self._run(r, m, files),
        ).grid(row=0, column=1, rowspan=2, padx=8, pady=8)

    def _run(self, recipe_id: str, message: str, files: list[str]) -> None:
        project = ""
        if self.get_project:
            try:
                project = self.get_project() or ""
            except Exception:
                project = ""
        task_id = ""
        try:
            from cli.recipes import emit_recipe
            path = emit_recipe(recipe_id, project=project)
            task_id = path.stem if path else ""
            self._status.configure(text=f"В очереди: {path.name}")
        except Exception as exp:
            # fallback: local queue put
            try:
                from core.local_queue import enqueue_desktop_task
                from ui.paths import agentbus_root
                tid = enqueue_desktop_task(
                    message or f"Рецепт {recipe_id}",
                    project=project,
                    files=files,
                    root=agentbus_root(),
                )
                task_id = str(tid or "")
                self._status.configure(text=f"В очереди: {tid}")
            except Exception as exp2:
                self._status.configure(text=f"Ошибка: {exp2 or exp}")
                return
        if self.on_enqueue:
            try:
                self.on_enqueue({
                    "recipe": recipe_id,
                    "message": message,
                    "files": files,
                    "task_id": task_id,
                })
            except Exception:
                pass
        try:
            from ui.dispatcher_ctl import is_running as _disp_run
            if not _disp_run():
                self._status.configure(
                    text=(self._status.cget("text") or "") + " · ▶ запустите диспетчер"
                )
        except Exception:
            pass
