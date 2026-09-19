# -*- coding: utf-8 -*-
"""Pure empty-state text for Plan panel."""
from __future__ import annotations


def plan_empty_text(*, has_project: bool, has_steps: bool = False) -> str:
    if not has_project:
        return (
            "Нет проекта\n\n"
            "Откройте папку через Setup / Explorer.\n"
            "Living Plan хранится в .agentbus/ и привязан к проекту."
        )
    if not has_steps:
        return (
            "План пуст\n\n"
            "• «+» — добавить шаг\n"
            "• Project Center → Advisor / Workflow → в план\n"
            "• Chat: MODIFY/REPLAN → Decision A/B/C\n"
            "• Continue — enqueue первого pending\n\n"
            "PEV current_plan.md — отдельный слой (вкладка PEV)."
        )
    return ""
