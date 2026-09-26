# -*- coding: utf-8 -*-
"""Pytest bootstrap: AgentBus root + src/ on sys.path (package imports only)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
for p in (SRC, ROOT):
    s = str(p)
    if s not in sys.path:
        sys.path.insert(0, s)


@pytest.fixture
def python_exe() -> str:
    """Интерпретатор, на котором проверяем запуск воркера.

    AGENTBUS_TEST_PYTHON позволяет прогнать проверку на другом Python,
    по умолчанию берётся тот, в котором запущен pytest.
    """
    return os.environ.get("AGENTBUS_TEST_PYTHON") or sys.executable


@pytest.fixture(autouse=True)
def _restore_feature_flags():
    """Ни один тест не должен оставлять изменённым config/feature_flags.yaml.

    set_flag() пишет прямо в файл проекта. Без восстановления прогон тестов
    оставлял репозиторий грязным, а результат зависел от порядка: тест,
    включавший флаг, ломал следующий, который проверяет его выключение.
    """
    try:
        from core import feature_flags as ff

        path = ff.config_path()
    except Exception:
        yield
        return

    saved = path.read_bytes() if path and path.is_file() else None
    try:
        yield
    finally:
        if saved is not None:
            try:
                path.write_bytes(saved)
                ff.reload_flags()
            except Exception:
                pass
