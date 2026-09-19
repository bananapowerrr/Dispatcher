# -*- coding: utf-8 -*-
"""Pure empty-state for Changes panel."""
from __future__ import annotations


def changes_empty_text(*, has_project: bool) -> str:
    if not has_project:
        return (
            "Выберите проект (Setup / Explorer)\n\n"
            "Изменения git и pending agent diffs появятся здесь."
        )
    return (
        "Нет изменений в рабочей копии\n\n"
        "• Agent Apply → файлы попадут в Changes\n"
        "• Review / Diff / Undo — справа или в чате\n"
        "• Stage / Discard — только для git-tracked правок"
    )
