# -*- coding: utf-8 -*-
"""Single entry for UI → Application services (product surface).

Does not replace individual services; only wires defaults for panels.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any


class AppFacade:
    """Lazy handles to Application API for one project root."""

    def __init__(self, project_root: str | Path | None = None):
        self.root = Path(project_root).resolve() if project_root else None

    def set_root(self, project_root: str | Path | None) -> None:
        self.root = Path(project_root).resolve() if project_root else None

    def project(self):
        from app.project_service import ProjectService
        return ProjectService(self.root)

    def tasks(self):
        from app.tasks_service import TasksService
        return TasksService(self.root)

    def plan(self):
        from app.plan_service import PlanService
        return PlanService(self.root)

    def apply_plan_input(self, message: str, **kw):
        from app.plan_service import apply_input_policy
        if not self.root:
            return {"ok": False, "error": "no project"}
        return apply_input_policy(self.root, message, **kw)

    def resolve_plan_decision(self, decision_id: str, option_id: str):
        from app.plan_service import resolve_plan_decision
        if not self.root:
            return {"ok": False, "error": "no project"}
        return resolve_plan_decision(self.root, decision_id, option_id)

    def agent(self):
        from app.agent_service import AgentService
        return AgentService(self.root)

    def changes(self):
        from app.changes_service import ChangesService
        return ChangesService(self.root)

    def files(self):
        from app.files_service import FilesService
        return FilesService(self.root)

    def behavior(self):
        from app.agent_behavior import effective_behavior
        return effective_behavior(self.root)

    def health_text(self) -> str:
        try:
            return self.project().get_health_text()
        except Exception as e:
            return f"Health unavailable: {e}"

    def queue_summary(self) -> dict[str, Any]:
        try:
            return self.tasks().list_queue_summary() or {}
        except Exception:
            return {}

    def suggestions_text(self) -> str:
        try:
            return (self.agent().suggestions() or {}).get("text") or ""
        except Exception as e:
            return f"Suggestions: {e}"

    def empty_message(self, kind: str) -> str:
        """Unified empty-state copy."""
        try:
            from ui.i18n_ui import t as _t
        except Exception:
            def _t(k, default=""):
                return default
        mapping = {
            "queue": _t("queue_empty", default="Очередь пуста"),
            "history": _t("history_empty", default="Пусто — отправь задачу из чата"),
            "project": _t("no_project", default="Выберите проект"),
            "selection": _t("no_selection", default="Ничего не выбрано"),
            "changes": _t("changes_empty", default="Нет сохранённых изменений"),
        }
        return mapping.get(kind, _t("no_selection", default="—"))


_DEFAULT: AppFacade | None = None


def get_app(project_root: str | Path | None = None) -> AppFacade:
    global _DEFAULT
    if project_root is not None:
        return AppFacade(project_root)
    if _DEFAULT is None:
        _DEFAULT = AppFacade()
    return _DEFAULT
