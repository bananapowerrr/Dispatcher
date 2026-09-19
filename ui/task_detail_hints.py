# -*- coding: utf-8 -*-
"""Pure empty-state for Task Detail."""
from __future__ import annotations


def task_detail_empty_text() -> str:
    return (
        "Нет выбранной задачи\n\n"
        "• Клик по строке в Queue или History\n"
        "• После DONE/ERROR — карточка в History\n"
        "• Здесь: status · phases · files · trace · result\n\n"
        "Один task_id = один observable lifecycle (FSM)."
    )
