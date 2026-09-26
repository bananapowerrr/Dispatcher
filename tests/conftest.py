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
