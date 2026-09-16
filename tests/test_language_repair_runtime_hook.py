# -*- coding: utf-8 -*-
from __future__ import annotations

from language_guard import (
    needs_language_repair,
    language_repair_message,
    language_system_prompt,
    is_mostly_russian,
)


def test_english_prose_triggers_repair():
    text = "I need to refactor the router and add quota checks carefully."
    assert needs_language_repair(text) is True
    assert is_mostly_russian(text) is False


def test_russian_prose_ok():
    text = "Нужно отрефакторить router и добавить проверку квот."
    assert needs_language_repair(text) is False
    assert is_mostly_russian(text) is True


def test_code_blocks_ignored():
    text = (
        "Объяснение на русском.\n"
        "```python\n"
        "def foo():\n"
        "    return \"hello world from English string\"\n"
        "```\n"
        "Ещё русский текст про модуль.\n"
    )
    assert needs_language_repair(text) is False


def test_repair_message_ru():
    msg = language_repair_message("ru")
    assert "ЯЗЫК" in msg or "русск" in msg.lower()


def test_system_prompt_contains_negative_constraint():
    sp = language_system_prompt("ru")
    assert "ЗАПРЕЩЕНО" in sp or "русск" in sp.lower()
