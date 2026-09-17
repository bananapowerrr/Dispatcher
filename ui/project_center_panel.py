# -*- coding: utf-8 -*-
"""FC-43 Project Workspace — presentation over snapshot/audit/plan/decisions.

Not a new backend: aggregates ProjectService + TasksService into one panel.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

try:
    import customtkinter as ctk
except ImportError:  # pragma: no cover
    ctk = None  # type: ignore


class ProjectCenterPanel(ctk.CTkFrame if ctk else object):  # type: ignore
    """Project overview: status, next action, plan/decisions, audit."""

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
        self._next.pack(anchor="w", padx=12, pady=(0, 4), fill="x")

        self._meta = ctk.CTkLabel(self, text="", anchor="w", justify="left", text_color="gray")
        self._meta.pack(anchor="w", padx=12, pady=(0, 8), fill="x")

        self._body = ctk.CTkTextbox(self, height=280, wrap="word", font=ctk.CTkFont(family="Consolas", size=12))
        self._body.pack(fill="both", expand=True, padx=12, pady=4)

        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=12, pady=8)
        ctk.CTkButton(row, text="Обновить", width=90, command=self.refresh).pack(side="left", padx=3)
        ctk.CTkButton(row, text="Аудит", width=90, command=self._run_audit).pack(side="left", padx=3)
        ctk.CTkButton(row, text="Что дальше?", width=100, command=self._what_next)
        ctk.CTkButton(row, text="Health", width=70, command=self._health_refresh).pack(side="left", padx=3)
        ctk.CTkButton(row, text="План", width=70, command=self._show_plan).pack(side="left", padx=3)
        ctk.CTkButton(row, text="Решения", width=90, command=self._show_decisions).pack(side="left", padx=3)

    def _root(self) -> str:
        try:
            r = self._get_project()
            return ((r() if callable(r) else r) or "").strip()
        except Exception:
            return ""

    def _fire(self, action_id: str) -> None:
        if self._on_action:
            try:
                self._on_action(action_id)
            except Exception:
                pass

    def _sys_path(self) -> None:
        import sys
        base = Path(__file__).resolve().parents[1]
        if str(base / "src") not in sys.path:
            sys.path.insert(0, str(base / "src"))

    def refresh(self) -> None:
        root = self._root()
        if not root:
            self._status.configure(text="Выберите проект")
            self._next.configure(text="")
            self._meta.configure(text="")
            self._body.delete("1.0", "end")
            return
        try:
            self._sys_path()
            from app.project_service import ProjectService
            from app.tasks_service import TasksService

            ps = ProjectService(root)
            ts = TasksService(root)

            text = ps.get_snapshot_text(include_capabilities=False)
            snap = ps.get_snapshot(include_capabilities=False)

            self._title.configure(text=f"Проект: {snap.get('project_name') or Path(root).name}")
            status = snap.get("status_label") or snap.get("status") or "—"
            self._status.configure(text=str(status))
            nxt = snap.get("next_action") or ""
            self._next.configure(text=f"Дальше: {nxt}" if nxt else "")

            q = ts.list_queue_summary()
            buckets = q.get("buckets") or {}
            n_now = len(buckets.get("now") or [])
            n_wait = len(buckets.get("waiting") or [])
            n_next = len(buckets.get("next") or [])
            n_done = len(buckets.get("done") or [])
            n_def = len(buckets.get("deferred") or [])
            sup = ts.supervisor_status()
            arch = ps.architecture_banner()
            bits = [
                f"plan: now={n_now} wait={n_wait} next={n_next} done={n_done} def={n_def}",
                f"agent: {sup.get('label') or sup.get('reason') or '—'}",
            ]
            if arch:
                bits.append(arch[:80])
            self._meta.configure(text=" · ".join(bits))

            self._body.delete("1.0", "end")
            self._body.insert("1.0", text)
            self._fire("project_refreshed")
        except Exception as exp:
            self._status.configure(text=f"Ошибка: {exp}")

    def _run_audit(self) -> None:
        root = self._root()
        if not root:
            return
        try:
            self._sys_path()
            from app.project_service import ProjectService
            text = ProjectService(root).run_audit_text()
            self._body.delete("1.0", "end")
            self._body.insert("1.0", text)
            self._status.configure(text="Аудит готов")
            self._fire("audit_done")
        except Exception as exp:
            self._status.configure(text=f"Аудит: {exp}")

    def _what_next(self) -> None:
        root = self._root()
        if not root:
            return
        try:
            self._sys_path()
            from app.project_service import ProjectService
            from app.tasks_service import TasksService
            ps = ProjectService(root)
            ts = TasksService(root)
            snap = ps.get_snapshot(include_capabilities=False)
            lines = ["ЧТО ДЕЛАТЬ ДАЛЬШЕ", ""]
            nxt = snap.get("next_action") or ""
            if nxt:
                lines.append(f"1. {nxt}")
            q = ts.list_queue_summary()
            waiting = (q.get("buckets") or {}).get("waiting") or []
            if waiting:
                lines.append("")
                lines.append("Ждут решения:")
                for w in waiting[:5]:
                    lines.append(f"  • {w.get('title') or w.get('id')}")
            next_steps = (q.get("buckets") or {}).get("next") or []
            if next_steps:
                lines.append("")
                lines.append("В плане:")
                for s in next_steps[:5]:
                    lines.append(f"  ○ {s.get('title') or s.get('id')}")
            try:
                audit = ps.run_audit()
                findings = audit.get("findings") or audit.get("recommendations") or []
                if isinstance(findings, list) and findings:
                    lines.append("")
                    lines.append("Рекомендации аудита:")
                    for f in findings[:5]:
                        if isinstance(f, dict):
                            lines.append(f"  · {f.get('title') or f.get('message') or f}")
                        else:
                            lines.append(f"  · {f}")
            except Exception:
                pass
            arch = ps.architecture_banner()
            if arch:
                lines.append("")
                lines.append(f"Архитектура: {arch}")
            self._body.delete("1.0", "end")
            self._body.insert("1.0", "\n".join(lines))
            self._status.configure(text="Совет")
            self._fire("what_next")
        except Exception as exp:
            self._status.configure(text=f"Совет: {exp}")

    def _show_plan(self) -> None:
        root = self._root()
        if not root:
            return
        try:
            self._sys_path()
            from app.tasks_service import TasksService
            q = TasksService(root).list_queue_summary()
            buckets = q.get("buckets") or {}
            lines = ["ПЛАН / ОЧЕРЕДЬ", ""]
            for name, key in (
                ("Сейчас", "now"),
                ("Ожидают", "waiting"),
                ("Далее", "next"),
                ("Отложено", "deferred"),
                ("Готово", "done"),
            ):
                items = buckets.get(key) or []
                lines.append(f"{name} ({len(items)})")
                for it in items[:8]:
                    lines.append(f"  · [{it.get('status') or '?'}] {it.get('title') or it.get('id')}")
                lines.append("")
            self._body.delete("1.0", "end")
            self._body.insert("1.0", "\n".join(lines))
            self._status.configure(text="План")
            self._fire("show_plan")
        except Exception as exp:
            self._status.configure(text=f"План: {exp}")

    def _show_decisions(self) -> None:
        root = self._root()
        if not root:
            return
        try:
            self._sys_path()
            from app.tasks_service import TasksService
            items = TasksService(root).open_decisions()
            lines = ["РЕШЕНИЯ", ""]
            if not items:
                lines.append("(нет открытых решений)")
            for it in items[:15]:
                if isinstance(it, dict):
                    lines.append(f"• {it.get('title') or it.get('id') or it}")
                    if it.get("question"):
                        lines.append(f"  {str(it['question'])[:120]}")
                else:
                    lines.append(f"• {it}")
            self._body.delete("1.0", "end")
            self._body.insert("1.0", "\n".join(lines))
            self._status.configure(text=f"Решения: {len(items)}")
            self._fire("show_decisions")
        except Exception as exp:
            self._status.configure(text=f"Решения: {exp}")

    def _health_refresh(self) -> None:
        """FC-45B: show Project Health (snapshot + advice) in body."""
        root = self._root()
        if not root:
            self._body.delete("1.0", "end")
            self._body.insert("1.0", "Выберите проект")
            return
        try:
            from app.project_service import ProjectService
            text = ProjectService(root).get_health_text()
            self._body.delete("1.0", "end")
            self._body.insert("1.0", text)
            self._status.configure(text="Project Health")
        except Exception as exp:
            self._body.delete("1.0", "end")
            self._body.insert("1.0", f"Health error: {exp}")
