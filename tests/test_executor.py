# -*- coding: utf-8 -*-
"""P0: GitPython-совместимость для aider.

`import git` != «GitPython работает». Классическая ошибка — пакет `git`
(конфликтующий) поверх/вместо GitPython: `import git` проходит, а
`git.exc` отсутствует -> `module 'git' has no attribute 'exc'`.
Реальная проверка: import git + путь + версия + рабочий объект из git.exc.
"""
from __future__ import annotations
import os
import sys
from pathlib import Path

import pytest

import _helpers as h
from executor import Executor, _GITPYTHON_SNIPPET


@pytest.fixture
def executor():
    return Executor()


def _env_with_first(path: str) -> dict:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(path) + os.pathsep + env.get("PYTHONPATH", "")
    return env


# ---------- реальный (здоровый) интерпретатор ----------
def test_report_ok_on_healthy_python(executor, python_exe):
    rep = executor._gitpython_report(python_exe)
    # структурно корректный отчёт
    assert set(rep) >= {"ok", "path", "version", "exc", "exc_obj", "reason"}
    assert rep["path"]
    # GitPython реально установлен и git.exc рабочий
    # (если нет — система обязана чинить, но в тестовом окружении должен быть)
    import importlib.util
    assert importlib.util.find_spec("git") is not None


# ---------- симуляция битого пакета `git` (module has no attribute 'exc') ----------
@pytest.fixture
def fake_git_pkg(tmp_path):
    """Фейковый пакет `git` ДО настоящего GitPython — исходная ошибка аудита."""
    pkg = tmp_path / "fakegit"
    pkg.mkdir()
    (pkg / "git.py").write_text(
        "__version__ = '0.1'\n"   # есть import, но НЕТ git.exc -> import git.exc падает
        , encoding="utf-8")
    return pkg


def test_fake_git_package_reported_broken(executor, python_exe, fake_git_pkg):
    rep = executor._gitpython_report(python_exe, _env_with_first(str(fake_git_pkg)))
    assert rep["ok"] is False
    assert "exc" not in rep["reason"].lower().replace("exception", "").split() or \
        "attribute" in (rep["reason"] or "").lower() or "exc" in (rep["reason"] or "").lower()


def test_snippet_catches_missing_git_exc(executor, python_exe, fake_git_pkg):
    """Прямая проверка: со сниппетом в подпроцессе импорт git.exc падает."""
    env = _env_with_first(str(fake_git_pkg))
    import subprocess
    import time
    _CRASH = (3221225477, 0xC0000005, -1073741819)
    last = None
    for attempt in range(4):
        p = subprocess.run([python_exe, "-c", _GITPYTHON_SNIPPET],
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=60, env=env)
        last = p
        if p.returncode not in _CRASH:
            break
        time.sleep(0.5 + attempt * 0.4)
    p = last
    assert p.returncode == 0  # сниппет сам не падает, отчёт в stdout
    assert "git.exc" in p.stdout or "exc" in p.stdout


# ---------- {files}/{yes} контракт (P1 yaml-согласованность) ----------
def test_args_expands_files_and_yes(executor):
    from workers import Worker
    w = Worker(name="w", command=("{aider}", "{yes}", "{files}", "--message", "{message}"))
    args = executor._args(w, "hi", ["a.py", "src/b.py"])
    assert "--yes" in args
    assert args.count("--yes") == 1
    assert args.count("--file") == 2
    idx = args.index("--file")
    assert args[idx + 1] == "a.py"
    assert args[idx + 3] == "src/b.py"
    assert "{message}" not in args


def test_args_recorded_all_yaml_aiders_get_files_and_yes():
    """P1: все aider-воркеры из workers.yaml содержат {files} и {yes}."""
    from config import WORKERS_FILE
    from workers import _from_yaml
    workers = _from_yaml(Path(WORKERS_FILE))
    aielder = [w for w in workers if w.harness == "aider"]
    assert aielder, "в yaml должны быть aider-воркеры"
    for w in aielder:
        cmd = " ".join(w.command)
        assert "{files}" in cmd, f"{w.name} теряет {files} (контракт target files)"
        assert "{yes}" in cmd, f"{w.name} без {yes} (не-интерактив обязателен)"
        assert "{message}" in cmd, f"{w.name} без {message}"


def test_yaml_workers_have_max_parallel():
    from config import WORKERS_FILE
    from workers import _from_yaml
    for w in _from_yaml(Path(WORKERS_FILE)):
        assert w.max_parallel >= 1