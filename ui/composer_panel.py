# -*- coding: utf-8 -*-
"""Task Composer UI — explicit form over app.task_composer (not a new FSM)."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import customtkinter as ctk

from ui.i18n_ui import t as _t


class ComposerPanel(ctk.CTkFrame):
    """Fields: message, files, priority → preview → enqueue via callback."""

    def __init__(
        self,
        parent,
        *,
        get_project: Callable[[], str | None] | None = None,
        on_submit: Callable[[dict[str, Any]], None] | None = None,
        **kwargs,
    ):
        super().__init__(parent, **kwargs)
        self.get_project = get_project or (lambda: None)
        self.on_submit = on_submit
        self._build()

    def _build(self) -> None:
        ctk.CTkLabel(
            self,
            text=_t("composer_title", default="Composer — новая задача"),
            font=ctk.CTkFont(size=14, weight="bold"),
        ).pack(anchor="w", padx=10, pady=(10, 4))
        ctk.CTkLabel(
            self,
            text=_t(
                "composer_hint_panel",
                default="Не чат: явная форма. Отправка → очередь, не прямой worker.",
            ),
            text_color="gray",
            wraplength=420,
            justify="left",
        ).pack(anchor="w", padx=10, pady=(0, 8))

        ctk.CTkLabel(self, text=_t("composer_message", default="Задача")).pack(anchor="w", padx=10)
        self.msg = ctk.CTkTextbox(self, height=90)
        self.msg.pack(fill="x", padx=10, pady=4)

        row = ctk.CTkFrame(self)
        row.pack(fill="x", padx=10, pady=4)
        ctk.CTkLabel(row, text=_t("composer_files", default="Файлы (через запятую)")).pack(side="left")
        self.files_var = ctk.StringVar(value="")
        ctk.CTkEntry(row, textvariable=self.files_var, width=280).pack(side="left", padx=8)

        row2 = ctk.CTkFrame(self)
        row2.pack(fill="x", padx=10, pady=4)
        ctk.CTkLabel(row2, text=_t("composer_priority", default="Приоритет")).pack(side="left")
        self.prio = ctk.CTkOptionMenu(row2, values=["", "1", "2", "3", "4", "5"], width=80)
        self.prio.set("")
        self.prio.pack(side="left", padx=8)
        self.force_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(row2, text="force_refresh", variable=self.force_var).pack(side="left", padx=8)

        self.preview = ctk.CTkTextbox(self, height=100)
        self.preview.pack(fill="both", expand=True, padx=10, pady=6)
        self.preview.configure(state="disabled")

        btn = ctk.CTkFrame(self)
        btn.pack(fill="x", padx=10, pady=(0, 10))
        ctk.CTkButton(btn, text=_t("composer_preview_btn", default="Превью"), width=100, command=self._preview).pack(
            side="left", padx=4
        )
        ctk.CTkButton(
            btn,
            text=_t("composer_submit", default="В очередь"),
            width=120,
            command=self._submit,
        ).pack(side="left", padx=4)
        ctk.CTkButton(
            btn,
            text=_t("composer_from_suggest", default="Из подсказки"),
            width=130,
            command=self._from_suggest,
        ).pack(side="left", padx=4)
        self.status = ctk.CTkLabel(self, text="", text_color="gray")
        self.status.pack(anchor="w", padx=10, pady=(0, 8))

    def _compose(self) -> dict[str, Any]:
        from app.task_composer import compose_task

        msg = self.msg.get("1.0", "end").strip()
        files = [x.strip() for x in self.files_var.get().split(",") if x.strip()]
        prio = self.prio.get().strip()
        return compose_task(
            message=msg,
            project=self.get_project(),
            files=files or None,
            priority=int(prio) if prio.isdigit() else None,
            force_refresh=bool(self.force_var.get()),
            channel="desktop",
        )

    def _preview(self) -> None:
        from app.task_composer import format_composer_preview, validate_task_dict

        try:
            task = self._compose()
        except Exception as e:
            self.status.configure(text=str(e))
            return
        errs = validate_task_dict(task)
        self.preview.configure(state="normal")
        self.preview.delete("1.0", "end")
        self.preview.insert("1.0", format_composer_preview(task))
        if errs:
            self.preview.insert("end", "\n\nERR: " + "; ".join(errs))
        self.preview.configure(state="disabled")
        self.status.configure(text="OK" if not errs else "validation issues")

    def _submit(self) -> None:
        from app.task_composer import validate_task_dict

        try:
            task = self._compose()
            errs = validate_task_dict(task)
            if errs:
                self.status.configure(text="; ".join(errs))
                return
            if self.on_submit:
                self.on_submit(task)
            self.status.configure(text=f"queued {task.get('id')}")
            self.msg.delete("1.0", "end")
        except Exception as e:
            self.status.configure(text=str(e))

    def _from_suggest(self) -> None:
        try:
            from app.agent_service import AgentService
            from app.task_composer import compose_from_suggestion, format_composer_preview

            root = self.get_project()
            task = compose_from_suggestion(AgentService(root), 0, project=root)
            self.msg.delete("1.0", "end")
            self.msg.insert("1.0", task.get("message") or "")
            files = task.get("files") or []
            self.files_var.set(", ".join(files))
            self.preview.configure(state="normal")
            self.preview.delete("1.0", "end")
            self.preview.insert("1.0", format_composer_preview(task))
            self.preview.configure(state="disabled")
            self.status.configure(text="suggestion loaded — edit & queue")
        except Exception as e:
            self.status.configure(text=str(e))
