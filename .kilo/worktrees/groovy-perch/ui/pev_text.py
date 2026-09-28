# -*- coding: utf-8 -*-
"""Pure PEV panel text helpers (no GUI)."""
from __future__ import annotations


def pev_empty_text() -> str:
    """Placeholder when .agentbus/current_plan.md is missing."""
    return (
        "# PEV-план пока нет\n\n"
        "План появится после задачи с Plan-Execute-Verify\n"
        "(complexity / policy включает PEV).\n\n"
        "Файл: .agentbus/current_plan.md\n"
        "Можно набросать шаги вручную и нажать «Сохранить».\n"
        "Living Plan / Project Center — другой слой плана задач.\n"
    )
