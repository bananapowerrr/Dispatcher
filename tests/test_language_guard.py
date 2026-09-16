# -*- coding: utf-8 -*-
from language_guard import (
    check_russian_prose,
    needs_language_repair,
    language_system_prompt,
    format_stream_badge,
    set_agent_language,
    get_agent_language,
)


def test_russian_majority():
    assert check_russian_prose("Нужно открыть файл и добавить проверку квот.").ok
    assert not check_russian_prose(
        "I need to open the file and add a quota check for the router."
    ).ok


def test_code_ignored():
    text = "План:\n```python\ndef foo():\n    return 1\n```\nГотово."
    assert check_russian_prose(text).ok


def test_needs_repair_only_ru(monkeypatch):
    monkeypatch.setenv("AGENTBUS_LANG", "ru")
    set_agent_language("ru", persist=False)
    assert needs_language_repair("Completely English reasoning about the stack.")
    set_agent_language("en", persist=False)
    assert not needs_language_repair("Completely English reasoning about the stack.")


def test_system_prompt_ru_has_ban():
    set_agent_language("ru", persist=False)
    p = language_system_prompt("ru")
    assert "ЗАПРЕЩЕНО" in p or "русск" in p.lower()
    assert "ПРИМЕР" in p


def test_badge_localized():
    set_agent_language("ru", persist=False)
    assert "РАССУЖДЕНИЕ" in format_stream_badge("thinking", "ru")
    assert format_stream_badge("done", "en") == "DONE"
