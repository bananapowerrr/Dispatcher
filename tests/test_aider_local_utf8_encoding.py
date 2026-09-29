# -*- coding: utf-8 -*-
"""Регрессия: не-UTF-8 файл в репозитории ронял aider_local.

Источник: `.gitignore`, записанный в cp1251 (байт 0xf1). Aider при
построении repo-map читает каждый файл дерева и на UnicodeError печатает
"Use --encoding to set the unicode encoding." — для КАЖДОГО файла. Десятки
одинаковых строк n-guard принимал за петлю модели -> LOOP_ERROR ->
health_unavailable -> aider_local выпадал из пула.

Проверяем две вещи:
1. Текстовые файлы проекта обязаны декодироваться в UTF-8.
2. aider_local пишет UTF-8 по умолчанию, кириллица не портится.
"""
from __future__ import annotations

import pathlib
import shutil
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent

TEXT_SUFFIXES = {".py", ".md", ".yaml", ".yml", ".json", ".txt", ".cfg", ".ini", ".toml"}
SKIP_DIRS = {".git", "__pycache__", ".pytest_cache", "node_modules", ".agentbus"}


def _ollama_alive() -> bool:
    exe = shutil.which("ollama")
    if not exe:
        return False
    try:
        out = subprocess.run([exe, "list"], capture_output=True, text=True, timeout=20)
        return out.returncode == 0
    except Exception:
        return False


def test_repo_text_files_are_utf8() -> None:
    """Каждый текстовый файл проекта обязан читаться как UTF-8.

    Именно этот тест поймал исходный дефект: cp1251-байты в .gitignore.
    """
    bad: list[str] = []
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        try:
            path.read_bytes().decode("utf-8")
        except UnicodeDecodeError as exc:
            bad.append(f"{path.relative_to(ROOT)}: {exc}")
    assert not bad, "файлы не в UTF-8:\n" + "\n".join(bad)


def test_aider_local_writes_utf8(tmp_path: pathlib.Path) -> None:
    """aider_local обязан записать кириллицу как валидный UTF-8."""
    if not _ollama_alive():
        pytest.skip("ollama недоступна")
    sys.path[:0] = [str(ROOT / "src"), str(ROOT)]
    from core.executor import Executor
    from core.workers import Worker, _command_tokens

    raw = (ROOT / "config" / "workers.yaml").read_text(encoding="utf-8")
    import yaml

    data = yaml.safe_load(raw)
    workers = data if isinstance(data, list) else (data.get("workers") or [])
    entry = dict(next(w for w in workers if w.get("name") == "aider_local"))
    entry["command"] = _command_tokens(entry.get("command"))
    worker = Worker(**entry)

    target = tmp_path / "utf8_check.py"
    target.write_text("", encoding="utf-8")  # та же заглушка, что даёт рантайм

    result = Executor().run_foreign(
        worker, "ollama", str(tmp_path),
        "Create file utf8_check.py with function privet() that returns string мир",
        300, [str(target)],
    )
    output = (result.stdout or "") + (result.stderr or "")
    assert "Use --encoding" not in output, (
        "aider сообщил об ошибке кодировки — в репозитории не-UTF-8 файл:\n" + output[-1500:]
    )
    assert target.stat().st_size > 0, "файл остался пустым"
    text = target.read_text(encoding="utf-8")
    assert "def privet" in text, text
    assert "мир" in text, "кириллица не записана как UTF-8"
