# -*- coding: utf-8 -*-
"""core.verify._argv(): кавычки в команде проверки.

Регрессия: shlex.split(posix=False) оставлял кавычки в токенах, поэтому
`python -m py_compile "f.py"` уходил в subprocess как имя файла вместе с
кавычками и падал с [Errno 22] Invalid argument. Реальная задача в рантайме
уходила в DEFERRED с ENV_ERROR вместо честной верификации.

Просто убрать кавычки из команды нельзя: корень проекта бывает с пробелами
("F:\\Мой диск\\AgentBus"). Поэтому кавычки снимаются на разборе аргументов.
"""
from __future__ import annotations

from pathlib import Path

from core.verify import _argv, _unquote, run_command


def test_unquote_strips_only_paired_outer_quotes():
    assert _unquote('"a.py"') == "a.py"
    assert _unquote("'a.py'") == "a.py"
    assert _unquote("a.py") == "a.py"
    assert _unquote('"') == '"'              # одиночная кавычка — не пара
    assert _unquote('say "hi"') == 'say "hi"'  # внутренние не трогаем
    assert _unquote("") == ""


def test_py_compile_filename_has_no_quotes():
    argv = _argv('python -m py_compile "test_gate_ok.py"')
    assert argv[-1] == "test_gate_ok.py"


def test_path_with_spaces_survives_quoting():
    argv = _argv('python -m py_compile "my dir/f.py"')
    assert argv[-1] == "my dir/f.py"


def test_multiple_files_all_unquoted():
    argv = _argv('python -m py_compile "a.py" "b.py" "c.py"')
    assert argv[-3:] == ["a.py", "b.py", "c.py"]


def test_pytest_still_routed_to_python_module():
    argv = _argv("pytest -q tests")
    assert argv[1:3] == ["-m", "pytest"]
    assert argv[-1] == "tests"


def test_real_run_on_path_with_spaces(tmp_path):
    """Решающий тест: настоящий subprocess, путь с пробелом."""
    d = tmp_path / "my dir with spaces"
    d.mkdir(parents=True, exist_ok=True)
    (d / "m.py").write_text("x = 1\n", encoding="utf-8")
    res = run_command(
        f'python -m py_compile "{d.name}/m.py"',
        cwd=tmp_path, timeout=60, retries=1,
    )
    assert res.ok, res.output
    assert res.code == 0
