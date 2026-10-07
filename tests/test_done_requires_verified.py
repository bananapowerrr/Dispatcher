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
    assert verification_allows_done({"verification": {"ok": True}}) is True
    assert verification_allows_done({"verify": "PASS"}) is True
    # tests_passed — только вместе с worker (исторический путь успеха)
    assert verification_allows_done({"worker": "aider_local", "tests_passed": True}) is True
    assert verification_allows_done({"tests_passed": True}) is False
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


def test_verify_runs_on_success(tmp_path) -> None:
    """verify-команды задачи должны выполняться на success-пути.

    Регрессия f-aiders-033722: aider вернул exit 0 и создал рабочий файл,
    но verify не выполнялся, поэтому _save() писал verified=False — что
    неотличимо от «проверка провалилась».
    """
    import sys
    sys.path[:0] = [str(ROOT / "src"), str(ROOT)]
    from core.rp_llm import RPLlmMixin

    class _Stub(RPLlmMixin):
        def __init__(self, root):
            self.context = type("C", (), {"root": root})()

    class _Task:
        id = "t1"
        verify = []

    stub = _Stub(tmp_path)
    (tmp_path / "ok.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")

    # дефолтная проверка для .py без явных verify-команд
    ok, detail = stub._verify_success(_Task(), None, ["ok.py"])
    assert ok is True, detail
    assert "default_py_compile" in detail, detail

    # битый синтаксис обязан провалить проверку
    (tmp_path / "bad.py").write_text("def add(a, b)\n    return\n", encoding="utf-8")
    ok_bad, detail_bad = stub._verify_success(_Task(), None, ["bad.py"])
    assert ok_bad is False, "битый синтаксис не должен проходить верификацию"
    assert "default_py_compile" in detail_bad

    # проверять нечего -> True с явной пометкой, а не молчаливый False
    ok_none, detail_none = stub._verify_success(_Task(), None, ["missing.py"])
    assert ok_none is True
    assert "no_verify_commands" in detail_none


def test_verify_success_uses_task_commands(tmp_path) -> None:
    """Явные verify-команды задачи имеют приоритет над дефолтом."""
    import sys
    sys.path[:0] = [str(ROOT / "src"), str(ROOT)]
    from core.rp_llm import RPLlmMixin

    class _Stub(RPLlmMixin):
        def __init__(self, root):
            self.context = type("C", (), {"root": root})()

    stub = _Stub(tmp_path)
    (tmp_path / "ok.py").write_text("x = 1\n", encoding="utf-8")

    class _TaskFail:
        id = "t2"
        # Без кавычек: core.verify._argv() не снимает кавычки, и
        # `python -c "import sys; sys.exit(3)"` выполняется как строковый
        # литерал -> exit 0. Это отдельный баг _argv, не проверяем его здесь.
        verify = [f'{sys.executable} verify_should_fail.py']

    ok, detail = stub._verify_success(_TaskFail(), None, ["ok.py"])
    assert ok is False, "падающая команда задачи обязана давать ERROR"
    assert "task_verify" in detail, detail


def _baseline_helpers():
    import sys
    sys.path[:0] = [str(ROOT / "src"), str(ROOT)]
    from core.rp_llm import _task_baseline, _task_changed
    return _task_baseline, _task_changed


class _FileTask:
    def __init__(self, files):
        self.files = files
        self.id = "t"


def test_task_scoped_baseline_ignores_unrelated_changes(tmp_path) -> None:
    """Чужие правки в дереве не должны выдаваться за результат задачи.

    Регрессия s-short-035301: в changed_files попадали 11 посторонних
    файлов, задача получала DONE при собственном файле 0 Б.
    """
    import subprocess
    _base, changed = _baseline_helpers()
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, capture_output=True)
    for i in range(11):
        (tmp_path / f"unrelated_{i}.py").write_text(f"x = {i}\n", encoding="utf-8")

    task = _FileTask(["target.py"])
    baseline = _base(tmp_path, task)
    (tmp_path / "target.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")

    got = changed(tmp_path, task, baseline)
    assert got == ["target.py"], f"в changed попали чужие файлы: {got}"


def test_task_scoped_baseline_detects_real_change(tmp_path) -> None:
    """Воркер записал код в заглушку — это настоящее изменение."""
    _base, changed = _baseline_helpers()
    task = _FileTask(["target.py"])
    (tmp_path / "target.py").write_text("", encoding="utf-8")  # заглушка
    baseline = _base(tmp_path, task)
    (tmp_path / "target.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    assert changed(tmp_path, task, baseline) == ["target.py"]


def test_task_scoped_baseline_rejects_empty_file(tmp_path) -> None:
    """Заглушка осталась 0 Б — изменения нет, DONE недопустим."""
    _base, changed = _baseline_helpers()
    task = _FileTask(["target.py"])
    (tmp_path / "target.py").write_text("", encoding="utf-8")
    baseline = _base(tmp_path, task)
    assert changed(tmp_path, task, baseline) == [], "пустая заглушка не должна считаться изменением"


def test_task_scoped_baseline_missing_file_stays_missing(tmp_path) -> None:
    """Файл не создан вовсе — тоже не изменение."""
    _base, changed = _baseline_helpers()
    task = _FileTask(["absent.py"])
    baseline = _base(tmp_path, task)
    assert changed(tmp_path, task, baseline) == []


def test_empty_file_cannot_pass_py_compile_claim(tmp_path) -> None:
    """Пустой файл синтаксически валиден: py_compile проходит на пустоте.

    Поэтому непустота проверяется по размеру ДО запуска verify, иначе
    «верификация успешна» означала бы «воркер ничего не написал».
    """
    import subprocess
    import sys
    empty = tmp_path / "empty.py"
    empty.write_text("", encoding="utf-8")
    out = subprocess.run(
        [sys.executable, "-m", "py_compile", str(empty)],
        capture_output=True, text=True, cwd=tmp_path)
    assert out.returncode == 0, "пустой файл действительно проходит py_compile"


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


def test_changed_paths_ignores_empty_stub(tmp_path) -> None:
    """Заглушка 0 Б — не результат работы, а артефакт Executor.

    Без этой проверки guard обманывается собственной заглушкой:
    aider уходит в чат, файл остаётся пустым, git status показывает
    «изменение», и задача снова получает DONE (a-aiders-033140).
    """
    import subprocess
    import sys
    sys.path[:0] = [str(ROOT / "src"), str(ROOT)]
    from core.rp_llm import _changed_paths

    subprocess.run(["git", "init", "-q"], cwd=tmp_path, capture_output=True)
    (tmp_path / "stub.py").write_text("", encoding="utf-8")
    (tmp_path / "real.py").write_text("x = 1\n", encoding="utf-8")
    found = _changed_paths(None, project=str(tmp_path), task=None)
    assert "stub.py" not in found, "пустая заглушка не должна считаться изменением"
    assert "real.py" in found, "настоящий файл должен учитываться"
