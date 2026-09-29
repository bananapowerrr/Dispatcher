# -*- coding: utf-8 -*-
"""DONE недопустим без верификации или реальных изменений.

Регресс 2026-09-29 (задача e2e-031910): opencode вернул exit 0 со
stdout «[PLAN] 1. Создать файл…», ничего не изменив. rp_llm считал это
успехом (`if result.ok:`) и вызывал queue.finish(..., "DONE") НАПРЯМУЮ,
минуя finish_task -> enforce_done_contract. Итог: DONE, verified=False,
файл 0 Б. Система рапортовала успех на пустом результате.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


# ---------- контракт ----------
def test_done_requires_verified_true() -> None:
    """enforce_done_contract понижает DONE без верификации до ERROR."""
    from core.terminal_path import enforce_done_contract

    # Ничего не менял, верификации нет -> DONE недопустим
    state, res = enforce_done_contract("DONE", {"worker": "opencode", "stdout": "[PLAN] ..."})
    assert state != "DONE", "DONE без верификации должен понижаться"
    assert res.get("verified") is False
    assert res.get("error")

    # Явная верификация -> DONE допустим
    state, _ = enforce_done_contract("DONE", {"verified": True})
    assert state == "DONE"


def test_verification_allows_done_matrix() -> None:
    from core.terminal_path import verification_allows_done

    assert verification_allows_done({"verified": True}) is True
    assert verification_allows_done({"tests_passed": True}) is True
    assert verification_allows_done({"verification": {"ok": True}}) is True
    # голый stdout без верификации — не повод для DONE
    assert verification_allows_done({"worker": "opencode", "stdout": "создал файл!"}) is False


# ---------- обходные пути ----------
def test_rp_llm_does_not_finish_done_without_changes() -> None:
    """rp_llm обязан проверять изменения перед queue.finish(..., 'DONE')."""
    src = _read("src/core/rp_llm.py")
    assert "_changed_paths" in src, "нет проверки реально изменённых файлов"
    assert "no_changes_and_no_verification" in src, (
        "нет fail-closed причины для DONE без изменений"
    )
    # в блоке if result.ok: обязан быть fail-closed до queue.finish
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_changed_paths":
            break
    else:
        pytest.fail("_changed_paths не найден")


def test_rp_llm_fail_closed_before_queue_finish() -> None:
    """Порядок: проверка ДО прямого queue.finish(..., 'DONE')."""
    src = _read("src/core/rp_llm.py")
    guard = src.find("no_changes_and_no_verification")
    finish = src.find('self.queue.finish(task.id, self.worker_id, "DONE"')
    assert guard != -1, "нет guard"
    assert finish != -1, "нет прямого queue.finish в rp_llm"
    assert guard < finish, "guard должен стоять ДО queue.finish(DONE)"


def test_explicit_verified_helper() -> None:
    import sys
    sys.path[:0] = [str(ROOT / "src"), str(ROOT)]
    from core.rp_llm import _explicit_verified

    class R:
        def __init__(self, **kw):
            self.__dict__.update(kw)

        def to_dict(self):
            return dict(self.__dict__)

    assert _explicit_verified(R(verified=True)) is True
    assert _explicit_verified(R(tests_passed=True)) is True
    assert _explicit_verified(R(verification={"ok": True})) is True
    # модель написала «файл создан» в тексте — это не верификация
    assert _explicit_verified(R(stdout="Created the file successfully")) is False
    assert _explicit_verified(R(stdout="[PLAN] 1. Создать файл")) is False


def test_changed_paths_detects_real_change(tmp_path) -> None:
    """Проверка идёт по git status, а не по словам модели."""
    import subprocess
    import sys
    sys.path[:0] = [str(ROOT / "src"), str(ROOT)]
    from core.rp_llm import _changed_paths

    (tmp_path / "new_file.py").write_text("x = 1\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, capture_output=True)
    found = _changed_paths(None, project=str(tmp_path), task=None)
    assert "new_file.py" in found, f"изменение не найдено: {found}"
