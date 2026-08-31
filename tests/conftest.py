# -*- coding: utf-8 -*-
"""Фикстуры и общий вход для регрессионного suite AgentBus.

ВНИМАНИЕ: env задаётся ДО импорта модулей AgentBus — config.py читает окружение
и .env при первом импорте. После импорта конфиг зафиксирован на temp-корень.
"""
import os
import sys
import tempfile
from pathlib import Path

# --- изоляция от рабочего окружения (до любых import config/runtime) ---
_TMP = Path(tempfile.mkdtemp(prefix="agentbus-tests-"))
os.environ["AGENTBUS_ROOT"] = str(_TMP)
os.environ["AGENTBUS_WORKERS_STATE"] = str(_TMP / "workers_state.json")
os.environ["PROJECT_PREDICTION_ANALYZER"] = ""
os.environ["SUPABASE_URL"] = ""
os.environ["SUPABASE_SERVICE_ROLE_KEY"] = ""
os.environ["AGENTBUS_GIT_IGNORE"] = (
    "__pycache__/,*.pyc,.pytest_cache/,*.aider*,*.aider.*-a,*.orig,*.rej,.tmp/,*.tmp"
)
# скрытый бесконечный retry не должен сработать в тестах
os.environ["AGENTBUS_MAX_ATTEMPTS"] = os.getenv("AGENTBUS_MAX_ATTEMPTS", "3")
os.environ["AGENTBUS_HEALTH_BASE_COOLDOWN"] = "10"

# рабочий python для subprocess-проверок (не 'python' — битый WindowsApps shim)
_PY = os.getenv("AGENTBUS_TEST_PYTHON", "")
if not _PY:
    for cand in (
        Path(os.environ.get("AIDER_PYTHON", "")),
        Path("C:/Users/user/AppData/Local/Programs/Python/Python312/python.exe"),
    ):
        if str(cand) and Path(cand).is_file():
            _PY = str(cand)
            break
if not _PY:
    _PY = sys.executable
os.environ["AGENTBUS_TEST_PYTHON"] = _PY

import pytest  # noqa: E402


@pytest.fixture
def python_exe():
    return _PY