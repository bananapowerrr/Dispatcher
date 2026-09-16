# -*- coding: utf-8 -*-
"""Diff preview panel: Apply / Reject pending file changes."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

import customtkinter as ctk

from ui.paths import agentbus_root, ensure_sys_path


class DiffPanel(ctk.CTkFrame):
    """Shows unified diffs for a task and Apply/Reject actions."""

    def __init__(
        self,
        parent,
        *,
        get_project_root: Callable[[], str] | None = None,
        on_applied: Callable[[str], None] | None = None,
        on_rejected: Callable[[str], None] | None = None,
    ):
        super().__init__(parent)
        self.get_project_root = get_project_root or (lambda: "")
        self.on_applied = on_applied
        self.on_rejected = on_rejected
        self._task_id: str = ""

        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=8, pady=4)
        ctk.CTkLabel(top, text="Diff", font=ctk.CTkFont(size=14, weight="bold")).pack(side="left")
        self.status = ctk.CTkLabel(top, text="", text_color="gray")
        self.status.pack(side="left", padx=8)

        self.text = ctk.CTkTextbox(self, state="disabled", wrap="none", font=ctk.CTkFont(family="Consolas", size=12))
        self.text.pack(fill="both", expand=True, padx=8, pady=4)

        btn = ctk.CTkFrame(self, fg_color="transparent")
        btn.pack(fill="x", padx=8, pady=6)
        ctk.CTkButton(btn, text="Apply", command=self.apply, fg_color="#2d6a4f", width=100).pack(side="left", padx=4)
        ctk.CTkButton(btn, text="Reject", command=self.reject, fg_color="#6c757d", width=100).pack(side="left", padx=4)
        ctk.CTkButton(btn, text="Refresh", command=self.refresh_from_store, width=90).pack(side="right", padx=4)

    def show_diff_text(self, task_id: str, diff_text: str) -> None:
        self._task_id = task_id
        self.status.configure(text=f"task={task_id}" if task_id else "")
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.insert("1.0", diff_text or "(empty diff)")
        self.text.configure(state="disabled")

    def show_for_task(self, task_id: str) -> None:
        self._task_id = task_id
        ensure_sys_path()
        try:
            from diff_engine import _store
            path = _store()
            if not path.is_file():
                self.show_diff_text(task_id, "Нет pending diffs")
                return
            data = json.loads(path.read_text(encoding="utf-8"))
            entry = data.get(task_id) or {}
            diffs = entry.get("diffs") or {}
            if not diffs:
                self.show_diff_text(task_id, "Нет diff для этой задачи")
                return
            blocks = []
            for rel, d in diffs.items():
                blocks.append(f"=== {rel} ===\n{d}")
            self.show_diff_text(task_id, "\n\n".join(blocks))
        except Exception as exc:
            self.show_diff_text(task_id, f"error: {exc}")

    def refresh_from_store(self) -> None:
        ensure_sys_path()
        try:
            from diff_engine import last_pending_diff_summary, _store
            path = _store()
            if not path.is_file():
                self.show_diff_text("", "Нет pending diffs")
                return
            data = json.loads(path.read_text(encoding="utf-8"))
            if not data:
                self.show_diff_text("", "Нет pending diffs")
                return
            tid = sorted(data.keys(), key=lambda k: float((data[k] or {}).get("ts") or 0), reverse=True)[0]
            self.show_for_task(tid)
            self.status.configure(text=last_pending_diff_summary())
        except Exception as exc:
            self.show_diff_text("", str(exc))

    def apply(self) -> None:
        if not self._task_id:
            self.refresh_from_store()
        if not self._task_id:
            return
        ensure_sys_path()
        try:
            from diff_engine import apply_pending
            root = self.get_project_root() or str(agentbus_root())
            result = apply_pending(self._task_id, project_root=root)
            if result.get("ok"):
                self.show_diff_text(self._task_id, f"APPLIED: {result.get('applied')}")
                if self.on_applied:
                    self.on_applied(self._task_id)
            else:
                self.show_diff_text(self._task_id, f"Apply failed: {result.get('error')}")
        except Exception as exc:
            self.show_diff_text(self._task_id, f"Apply error: {exc}")

    def reject(self) -> None:
        if not self._task_id:
            return
        ensure_sys_path()
        try:
            from diff_engine import reject_pending
            ok = reject_pending(self._task_id)
            self.show_diff_text(self._task_id, "REJECTED" if ok else "nothing to reject")
            if ok and self.on_rejected:
                self.on_rejected(self._task_id)
        except Exception as exc:
            self.show_diff_text(self._task_id, f"Reject error: {exc}")
