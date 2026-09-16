# -*- coding: utf-8 -*-
"""FC-38 Project Command Center panel — reads ProjectSnapshot / Audit."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

try:
    import customtkinter as ctk
except ImportError:  # pragma: no cover
    ctk = None  # type: ignore


class ProjectCenterPanel(ctk.CTkFrame if ctk else object):  # type: ignore
    """Shows project status, next action, sections, audit button."""

    def __init__(
        self,
        master,
        *,
        get_project: Callable[[], str] | None = None,
        on_action: Callable[[str], None] | None = None,
        **kwargs: Any,
    ):
        if ctk is None:
            raise RuntimeError("customtkinter required")
        super().__init__(master, **kwargs)
        self._get_project = get_project or (lambda: "")
        self._on_action = on_action
        self._title = ctk.CTkLabel(self, text="Проект", font=ctk.CTkFont(size=16, weight="bold"))
        self._title.pack(anchor="w", padx=12, pady=(12, 4))
        self._status = ctk.CTkLabel(self, text="—", anchor="w", justify="left")
        self._status.pack(anchor="w", padx=12, fill="x")
        self._next = ctk.CTkLabel(self, text="", anchor="w", justify="left", text_color="gray")
        self._next.pack(anchor="w", padx=12, pady=(0, 8), fill="x")
        self._body = ctk.CTkTextbox(self, height=280, wrap="word")
        self._body.pack(fill="both", expand=True, padx=12, pady=4)
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=12, pady=8)
        ctk.CTkButton(row, text="Обновить", width=100, command=self.refresh).pack(side="left", padx=4)
        ctk.CTkButton(row, text="Аудит", width=100, command=self._run_audit).pack(side="left", padx=4)
        ctk.CTkButton(row, text="Совет", width=100, command=lambda: self._fire("open_audit")).pack(side="left", padx=4)

    def _fire(self, action_id: str) -> None:
        if self._on_action:
            try:
                self._on_action(action_id)
            except Exception:
                pass

    def refresh(self) -> None:
        root = (self._get_project() or "").strip()
        if not root:
            self._status.configure(text="Выберите проект")
            self._body.delete("1.0", "end")
            return
        try:
            import sys
            base = Path(__file__).resolve().parents[1]
            if str(base / "src") not in sys.path:
                sys.path.insert(0, str(base / "src"))
            from intelligence.project_snapshot import build_project_snapshot
            snap = build_project_snapshot(root, include_capabilities=False)
            self._title.configure(text=f"Проект: {snap.project_name}")
            self._status.configure(text=f"{snap.status_label} ({snap.status})")
            self._next.configure(text=f"Дальше: {snap.next_action}" if snap.next_action else "")
            self._body.delete("1.0", "end")
            self._body.insert("1.0", snap.format_human())
        except Exception as exp:
            self._status.configure(text=f"Ошибка: {exp}")

    def _run_audit(self) -> None:
        root = (self._get_project() or "").strip()
        if not root:
            return
        try:
            import sys
            base = Path(__file__).resolve().parents[1]
            if str(base / "src") not in sys.path:
                sys.path.insert(0, str(base / "src"))
            from intelligence.project_audit import run_project_audit
            rep = run_project_audit(root)
            self._body.delete("1.0", "end")
            self._body.insert("1.0", rep.format_human())
            self._status.configure(text="Аудит готов")
            self._fire("audit_done")
        except Exception as exp:
            self._status.configure(text=f"Аудит: {exp}")
