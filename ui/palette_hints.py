# -*- coding: utf-8 -*-
"""Command palette empty / zero-match text."""
from __future__ import annotations


def palette_no_match_text(query: str = "") -> str:
    q = (query or "").strip()
    if not q:
        return (
            "Введите команду\n"
            "Примеры: plan · theme · help · doctor · queue · diff"
        )
    return (
        f"Ничего не найдено для «{q}»\n"
        "Попробуйте: plan, theme, help, doctor, settings, queue"
    )
