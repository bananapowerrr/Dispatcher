# -*- coding: utf-8 -*-
"""FC-42 Task Detail — one card: status, phases, files, trace, verify, result."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

try:
    import customtkinter as ctk
except ImportError:  # pragma: no cover
    ctk = None  # type: ignore


class TaskDetailPanel(ctk.CTkFrame if ctk else object):  # type: ignore
    """Shows a single task's observable lifecycle."""

    def __init__(
        self,
        master,
        *,
        get_project: Callable[[], str] | None = None,
        on_open_diff: Callable[[str], None] | None = None,
        on_open_file: Callable[[str], None] | None = None,
        **kwargs: Any,
    ):
        if ctk is None:
            raise RuntimeError("customtkinter required")
        super().__init__(master, **kwargs)
        self._get_project = get_project or (lambda: "")
        self._on_open_diff = on_open_diff
        self._on_open_file = on_open_file
        self._task_id = ""

        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=8, pady=4)
        ctk.CTkLabel(top, text="Task Detail", font=ctk.CTkFont(size=14, weight="bold")).pack(side="left")
        self._status_lbl = ctk.CTkLabel(top, text="", text_color="gray")
        self._status_lbl.pack(side="left", padx=10)
        ctk.CTkButton(top, text="↻", width=36, command=self.refresh).pack(side="right", padx=2)
        ctk.CTkButton(top, text="Diff", width=60, command=self._open_diff).pack(side="right", padx=2)

        self._title = ctk.CTkLabel(self, text="(выберите задачу в Queue)", anchor="w", font=ctk.CTkFont(size=13))
        self._title.pack(fill="x", padx=10, pady=(0, 4))

        self._body = ctk.CTkTextbox(self, wrap="word", font=ctk.CTkFont(family="Consolas", size=12))
        self._body.pack(fill="both", expand=True, padx=8, pady=4)

        self._hint = ctk.CTkLabel(self, text="", anchor="w", text_color="gray")
        self._hint.pack(fill="x", padx=10, pady=(0, 6))

    def show_task(self, task_id: str) -> None:
        self._task_id = (task_id or "").strip()
        self.refresh()

    def refresh(self) -> None:
        if not self._task_id:
            self._body.delete("1.0", "end")
            self._body.insert("1.0", "Нет выбранной задачи.")
            self._status_lbl.configure(text="")
            return
        root = ""
        try:
            r = self._get_project()
            root = (r() if callable(r) else r) or ""
        except Exception:
            root = ""
        try:
            import sys
            base = Path(__file__).resolve().parents[1]
            if str(base / "src") not in sys.path:
                sys.path.insert(0, str(base / "src"))
            from app.tasks_service import TasksService
            svc = TasksService(root or None)
            text = svc.format_detail_text(self._task_id)
            d = svc.get_task_detail(self._task_id)
            st = d.get("status") or ""
            self._status_lbl.configure(text=st)
            self._title.configure(text=(d.get("message") or self._task_id)[:120])
            self._body.delete("1.0", "end")
            self._body.insert("1.0", text or f"id={self._task_id}")
            files = d.get("files") or []
            self._hint.configure(text=f"files: {len(files)} · id={self._task_id[:16]}")
        except Exception as exp:
            self._body.delete("1.0", "end")
            self._body.insert("1.0", f"Ошибка загрузки: {exp}")

    def _open_diff(self) -> None:
        if self._task_id and self._on_open_diff:
            try:
                self._on_open_diff(self._task_id)
            except Exception:
                pass
