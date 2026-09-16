# -*- coding: utf-8 -*-
"""Skill matching helpers (Sprint C) — pure functions, no registry needed."""
from __future__ import annotations

from typing import Callable


COMPLEX_MARKERS = (
    "refactor", "рефактор", "rewrite", "перепиши", "implement",
    "реализуй", "добавь функционал", "add feature", "migrate",
    "миграц", "architecture", "архитектур", "redesign", "редизайн",
    "перепиши проект", "security audit", "across the codebase",
)


def is_complex_work(msg: str) -> bool:
    m = (msg or "").lower()
    return any(k in m for k in COMPLEX_MARKERS)


def match_cleanup(msg: str) -> str | None:
    m = msg.lower()
    if any(k in m for k in (
        "cleanup imports", "clean imports", "unused imports",
        "remove unused", "неиспользуемые импорты", "удали импорты",
        "убери импорты", "почисти импорты", "лишние импорты",
        "unused import", "f401",
    )):
        return "cleanup_imports"
    if any(k in m for k in (
        "format code", "format the code", "форматируй", "отформатируй",
        "приведи к стилю", "black", "reformat", "pep8", "pep 8",
    )):
        return "format_code"
    if any(k in m for k in (
        "sort imports", "isort", "отсортируй импорты", "сортировка импортов",
        "упорядочь импорты", "order imports",
    )):
        return "sort_imports"
    if any(k in m for k in (
        "print to logging", "replace print", "convert print",
        "замени print", "убери print", "print на logging",
    )):
        return "convert_print_to_logging"
    if any(k in m for k in (
        "trailing whitespace", "strip trailing", "пробел в конце",
        "лишние пробелы",
    )):
        return "strip_trailing_whitespace"
    if any(k in m for k in ("normalize newlines", "нормализуй перенос", "crlf")):
        return "normalize_newlines"
    if any(k in m for k in ("utf-8 coding", "coding: utf", "ensure utf")):
        return "ensure_utf8_coding"
    if any(k in m for k in ("count lines", "loc", "сколько строк")):
        return "count_lines"
    return None


def match_refactor(msg: str) -> str | None:
    m = msg.lower()
    if any(k in m for k in (
        "rename symbol", "rename function", "rename class",
        "переименуй", "переименовать",
    )):
        return "rename_symbol"
    if any(k in m for k in (
        "extract function", "extract method", "выдели функцию",
        "вынеси в функцию", "extract block",
    )):
        return "extract_function"
    return None


def match_analysis(msg: str) -> str | None:
    m = msg.lower()
    if any(k in m for k in (
        "bare open", "unhandled open", "find unsafe open",
        "голый open", "open без try", "небезопасный open",
    )):
        return "find_bare_io"
    if any(k in m for k in (
        "find todo", "find todos", "list todo", "list todos",
        "show todo", "найди todo", "список todo", "где todo",
        "где fixme", "find fixme",
    )) or m.strip() in {"todo", "todos", "fixme", "xxx", "hack"}:
        return "find_todos"
    if any(k in m for k in (
        "analyze complexity", "code complexity", "cyclomatic",
        "сложность кода", "анализ сложности",
    )):
        return "analyze_complexity"
    if any(k in m for k in (
        "run lint", "ruff check", "lint code", "проверь линтером",
        "запусти линтер", "запусти ruff", "pylint",
    )) and "fix" not in m and "исправ" not in m:
        return "run_lint"
    if any(k in m for k in (
        "check syntax", "syntax check", "проверь синтаксис", "compile check",
    )):
        return "check_syntax"
    if any(k in m for k in (
        "bare except", "naked except", "голый except", "except без типа",
        "find bare except", "найди bare except",
    )):
        return "find_bare_except"
    return None


def match_git(msg: str) -> str | None:
    m = msg.lower()
    if any(k in m for k in ("git status", "git snapshot", "снимок git", "snapshot")):
        return "git_snapshot"
    return None


def match_deps(msg: str) -> str | None:
    m = msg.lower()
    if any(k in m for k in (
        "list deps", "list dependencies", "список зависимостей", "список пакет",
    )):
        return "list_deps"
    if any(k in m for k in (
        "generate requirements", "сгенерируй requirements", "make requirements",
    )):
        return "generate_requirements"
    return None


def match_search(msg: str) -> str | None:
    m = msg.lower()
    if any(k in m for k in (
        "найди символ", "find symbol", "search symbol", "где определён",
        "where is defined",
    )):
        return "search_symbol"
    return None


MatchFn = Callable[[str], str | None]

DEFAULT_CHAIN: list[MatchFn] = [
    match_cleanup,
    match_refactor,
    match_analysis,
    match_git,
    match_deps,
    match_search,
]


def match_message(message: str, chain: list[MatchFn] | None = None) -> str | None:
    msg = (message or "").strip()
    if not msg:
        return None
    low = msg.lower()
    if is_complex_work(low):
        return None
    for fn in (chain or DEFAULT_CHAIN):
        hit = fn(low)
        if hit:
            return hit
    return None
