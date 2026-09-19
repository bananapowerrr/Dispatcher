# -*- coding: utf-8 -*-
"""Pure empty-state hints for Diff panel (no GUI)."""
from __future__ import annotations


def diff_empty_hint(*, task_id: str = "") -> str:
    if task_id:
        return (
            f"Нет diff для задачи {task_id}\n\n"
            "Возможно, worker не менял файлы, или changes ещё не записаны.\n"
            "Проверьте Changes / Source Control и Verify."
        )
    return (
        "Нет ожидающих diff\n\n"
        "После задачи с правками файлов:\n"
        "  1. Report / Review\n"
        "  2. вкладка Diff → Apply или Reject\n"
        "  3. или /diff · /apply · /undo в чате\n\n"
        "Пустой diff при git-less проекте — нормально, пока нет snapshot."
    )
