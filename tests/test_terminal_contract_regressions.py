# -*- coding: utf-8 -*-
"""Регрессы терминального контракта: verified и DONE-честность.

Найдено 2026-09-29 при разборе run-030427:
  * result.verified оставался None при УСПЕШНОМ DONE — _save() вычислял
    verified локально и клал только в evidence, но не в res;
  * навык, не изменивший ни одного файла, объявлял DONE (rp_cache_skills);
  * solution cache переигрывал такой ложный DONE;
  * неуспешная задача оставляла fingerprint в dedupe навсегда.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_save_writes_verified_into_result() -> None:
    """_save обязан записывать итог верификации в res (иначе verified=None)."""
    src = _read("src/core/runtime_ops.py")
    assert 'res["verified"] = verified' in src, (
        "_save() не пишет verified в res -> в файле задачи будет None"
    )


def test_skill_done_requires_changed_files() -> None:
    """Skill не может дать DONE, не изменив ни одного файла."""
    src = _read("src/core/rp_cache_skills.py")
    assert "files_changed" in src, "нет проверки изменённых файлов"
    # guard обязан возвращать пустой статус, а не DONE
    tree = ast.parse(src)
    found = False
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_finalize_skill_result":
            body = ast.unparse(node)
            found = True
            assert "files_changed" in body, (
                "_finalize_skill_result не проверяет изменённые файлы"
            )
            # пустой статус ("" / '') = «навык не решил», а не DONE
            empty = any(
                isinstance(n, ast.Return) and isinstance(n.value, ast.Constant)
                and n.value.value == ""
                for n in ast.walk(node)
            )
            assert empty, (
                "read-only навык должен возвращать пустой статус, а не DONE"
            )
    assert found, "_finalize_skill_result не найден"


def test_skill_miss_returns_none_not_empty_string() -> None:
    """'' считался терминалом: воркер не стартовал, задача висела до reclaim."""
    src = _read("src/core/rp_cache_skills.py")
    assert "return None" in src, (
        "после нерешённого навыка нужно return None, а не return status"
    )


def test_cache_requires_applied_files() -> None:
    """Solution cache не должен переигрывать ложный DONE."""
    src = _read("src/core/rp_cache_skills.py")
    assert "_apply_cached_solution" in src
    assert "written" in src, "кэш не проверяет, что файлы реально записаны"


def test_dedupe_released_on_failure() -> None:
    """Неудача не должна навсегда блокировать повтор той же задачи."""
    src = _read("src/core/runtime.py")
    assert "dedupe.forget" in src, (
        "при ERROR/DEFERRED/BLOCKED fingerprint не снимается -> "
        "повторная попытка вечно уходит в DEDUPED"
    )


def test_verification_gate_exists() -> None:
    """Метод _verification_engine_gate обязан существовать (DONE без него недостижим)."""
    from core.runtime import Runtime
    assert hasattr(Runtime, "_verification_engine_gate"), (
        "Runtime без _verification_engine_gate: rp_verify вызывает его, "
        "и любая задача падает с verification_gate_exception"
    )


def test_verification_gate_is_fail_closed() -> None:
    """Проверка не прошла -> не DONE."""
    from core.runtime import Runtime
    rt = Runtime.__new__(Runtime)

    class T:
        id = "x"
        message = "m"
        files = []
        verify = []
        metadata = {}

    ok, err = rt._verification_engine_gate(T(), None, execution_ok=True)
    assert ok is True and err == ""
    ok, err = rt._verification_engine_gate(T(), None, execution_ok=False)
    assert ok is False and err, "fail-closed нарушен: неуспех должен давать DONE"


def test_executor_creates_target_files() -> None:
    """Executor обязан создавать цели до старта воркера (иначе aider в чат)."""
    from core.executor import Executor
    assert hasattr(Executor, "_ensure_target_files")


def test_task_error_has_traceback_logging() -> None:
    """Причина ошибки должна попадать в лог, а не только '→ ERROR'."""
    ops = _read("src/core/runtime_ops.py")
    assert "traceback" in ops, "в finish_task нет traceback"
    life = _read("src/core/rp_lifecycle.py")
    assert "_log_task_error" in life, "в rp_lifecycle нет логирования причины"
    assert "PROJECT_<NAME>" in life, (
        "сообщение должно подсказывать, как завести проект в .env"
    )
