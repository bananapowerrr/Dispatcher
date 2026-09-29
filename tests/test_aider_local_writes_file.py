# -*- coding: utf-8 -*-
"""aider_local должен ЗАПИСЫВАТЬ код в файл, а не отвечать текстом.

Регресс 2026-09-29: задача run-030427 дошла до DONE, но hello.py весил
0 байт. Разбор показал, что aider не виноват:

    --file demo.py, файла нет  -> "Creating empty file", модель уходит в чат,
                                  правка не применяется (файл 1 Б)
    --file demo.py, файл есть  -> "Applied edit to demo.py" (8 Б)

Причина в том, что Executor._args() превращает {files} в "--file <name>",
а несуствующий файл aider трактует как повод для чат-ответа. Исправление:
Executor._ensure_target_files() создаёт пустые цели до старта воркера.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from core.executor import Executor

ROOT = Path(__file__).resolve().parents[1]
AIDER_PY = Path(os.getenv("AIDER_PYTHON", r"D:\Workspace\.venv-aider\Scripts\python.exe"))
AIDER_MODEL = os.getenv("AIDER_MODEL", "ollama_chat/qwen2.5-coder:7b")


# ---------- юнит: заглушки создаются до запуска ----------
def test_ensure_target_files_creates_missing(tmp_path: Path) -> None:
    created = Executor._ensure_target_files(str(tmp_path), ["a.py", "sub/b.py"])
    assert set(created) == {"a.py", "sub/b.py"}
    assert (tmp_path / "a.py").is_file()
    assert (tmp_path / "a.py").stat().st_size == 0
    assert (tmp_path / "sub" / "b.py").is_file()


def test_ensure_target_files_does_not_touch_existing(tmp_path: Path) -> None:
    f = tmp_path / "keep.py"
    f.write_text("x = 1\n", encoding="utf-8")
    assert Executor._ensure_target_files(str(tmp_path), ["keep.py"]) == []
    assert f.read_text(encoding="utf-8") == "x = 1\n"


def test_ensure_target_files_escapes_rejected(tmp_path: Path) -> None:
    """Писать за пределы проекта нельзя."""
    assert Executor._ensure_target_files(str(tmp_path), ["../evil.py"]) == []
    assert not (tmp_path.parent / "evil.py").exists()


def test_ensure_target_files_idempotent(tmp_path: Path) -> None:
    Executor._ensure_target_files(str(tmp_path), ["a.py"])
    assert Executor._ensure_target_files(str(tmp_path), ["a.py"]) == []


def test_ensure_target_files_empty_inputs(tmp_path: Path) -> None:
    assert Executor._ensure_target_files(str(tmp_path), []) == []
    assert Executor._ensure_target_files("", ["a.py"]) == []
    assert Executor._ensure_target_files(str(tmp_path), ["", "   "]) == []


# ---------- интеграция с реальным aider ----------
def _ollama_alive() -> bool:
    import urllib.request
    try:
        with urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=3):
            return True
    except Exception:
        return False


@pytest.mark.skipif(not AIDER_PY.is_file(), reason="aider-python не найден")
@pytest.mark.skipif(not _ollama_alive(), reason="ollama не отвечает")
def test_aider_local_writes_file(tmp_path: Path) -> None:
    """Требуемый регресс-тест: aider_local заполняет целевой файл.

    Сначала создаём заглушку (как это делает Executor), затем запускаем
    aider ровно той командой, которую собирает workers.yaml для aider_local.
    """
    target = tmp_path / "test_output.py"
    # ровно то, что теперь делает Executor до старта воркера
    Executor._ensure_target_files(str(tmp_path), ["test_output.py"])
    assert target.is_file(), "заглушка не создана"

    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    env["OLLAMA_API_BASE"] = env.get("OLLAMA_API_BASE", "http://127.0.0.1:11434")

    proc = subprocess.run(
        [str(AIDER_PY), "-X", "utf8", "-m", "aider",
         "--yes", "--model", AIDER_MODEL,
         "--no-auto-commits", "--no-pretty", "--no-stream",
         "--file", "test_output.py",
         "--message", "Add a function hello() that returns the string 'hi'. "
                      "Write only the code."],
        cwd=str(tmp_path), env=env, capture_output=True,
        text=True, encoding="utf-8", errors="replace", timeout=600,
    )
    out = (proc.stdout or "") + (proc.stderr or "")

    assert target.is_file(), f"файл не создан:\n{out[-2000:]}"
    body = target.read_text(encoding="utf-8")
    assert body.strip(), (
        "файл ПУСТ — aider ушёл в чат вместо правки "
        f"(проверь, что заглушка создана ДО запуска):\n{out[-2000:]}"
    )
    assert "def hello" in body, f"ожидалась функция hello, получено:\n{body[:500]}"
