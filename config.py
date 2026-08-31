# -*- coding: utf-8 -*-
from __future__ import annotations
import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parent

def _load_env_file(path: Path) -> None:
    if not path.is_file(): return
    try: lines = path.read_text(encoding="utf-8-sig").splitlines()
    except OSError: return
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#"): continue
        if line.startswith("export "): line = line[7:].lstrip()
        if "=" not in line: continue
        key, value = line.split("=", 1); key=key.strip(); value=value.strip()
        if len(value)>=2 and value[0]==value[-1] and value[0] in "\"'": value=value[1:-1]
        if key: os.environ.setdefault(key, value)

for env_path in (BASE_DIR/".env", ROOT_DIR/".env"):
    _load_env_file(env_path)

def _int(name: str, default: int) -> int:
    try: return int(os.getenv(name, str(default)))
    except (TypeError, ValueError): return default

def _float(name: str, default: float) -> float:
    try: return float(os.getenv(name, str(default)))
    except (TypeError, ValueError): return default

def _flag(name: str, default: bool = True) -> bool:
    """0/1/true/false/yes/no/on/off. Если env не задан — default (не `or True`,
    чтобы флаг реально можно было выключить)."""
    v = os.getenv(name, "").strip().lower()
    if not v:
        return default
    return v in {"1", "true", "yes", "on"}

# Единый корень AgentBus: автовывод из расположения config.py.
# AGENTBUS_ROOT в env — только явное переопределение (тесты, перенос).
AGENTBUS_ROOT = Path(os.getenv("AGENTBUS_ROOT", BASE_DIR))
BUS_ROOT = AGENTBUS_ROOT                       # историческое имя, всё ещё используется
CHANNELS_ROOT = AGENTBUS_ROOT / "channels"
# Внешние проекты — это НЕ часть AgentBus: задаются только через env / registry
# (PROJECT_<NAME>=<путь> в .env). Никаких хардкодов пользовательских путей.
PROJECT_ROOT = Path(os.getenv("PROJECT_PREDICTION_ANALYZER", "").strip()) \
    if os.getenv("PROJECT_PREDICTION_ANALYZER", "").strip() else None


def _load_projects() -> dict[str, Path]:
    """Реестр проектов из env-переменных PROJECT_<NAME>=<path>.

    Авторегистрирует Prediction-Analyzer из PROJECT_ROOT (обратная совместимость).
    Runtime НЕ хардкодит проекты — только резолвит через registry.
    """
    projects: dict[str, Path] = {}
    for key, value in os.environ.items():
        if key.startswith("PROJECT_") and value.strip():
            projects[key[len("PROJECT_"):]] = Path(value.strip())
    if "Prediction-Analyzer" not in projects and PROJECT_ROOT:
        projects["Prediction-Analyzer"] = PROJECT_ROOT
    return projects


PROJECTS = _load_projects()


def resolve_project(name: str) -> Path:
    """Возвращает корень внешнего проекта с понятной ошибкой, если не найден."""
    p = PROJECTS.get(str(name or "").strip())
    if not p:
        raise ValueError(
            f"Проект '{name}' не зарегистрирован. Добавьте PROJECT_{name}=<путь> "
            f"в .env (config.PROJECTS).")
    if not p.exists():
        raise FileNotFoundError(f"Директория проекта не существует: {p}")
    return p
SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
SUPABASE_KEY = (os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip() or os.getenv("SUPABASE_KEY", "").strip())

# --- Bus/polling ---
POLL_SECONDS = max(2, _int("AGENTBUS_POLL_SECONDS", 5))
WORKER_TIMEOUT = max(30, _int("AGENTBUS_WORKER_TIMEOUT", 900))
# Lease обязан быть БОЛЬШЕ максимального таймаута воркера, иначе задачу, которую
# воркер честно крутит, requeue_stale вернёт в PENDING и она выполнится дважды.
LEASE_SECONDS = max(WORKER_TIMEOUT + 120, _int("AGENTBUS_LEASE_SECONDS", 1200))
MAX_ATTEMPTS = max(1, _int("AGENTBUS_MAX_ATTEMPTS", 3))
VERIFY_TIMEOUT = max(30, _int("AGENTBUS_VERIFY_TIMEOUT", 300))
CHANNELS = tuple(x.strip() for x in os.getenv("AGENTBUS_CHANNELS", "gpt,grok,gemini").split(",") if x.strip())
DEFAULT_CHANNEL = os.getenv("AGENTBUS_DEFAULT_CHANNEL", "gpt").strip() or "gpt"

# --- Worker pool / registry ---
# Path to workers.yaml. Empty -> built-in registry.
WORKERS_FILE = os.getenv("AGENTBUS_WORKERS_FILE", "").strip() or (BASE_DIR / "workers.yaml")
PROVIDERS_FILE = os.getenv("AGENTBUS_PROVIDERS_FILE", "").strip() or (BASE_DIR / "providers.yaml")
# Персистентное состояние провайдеров (per provider:model): переживает рестарт.
PROVIDERS_STATE_FILE = os.getenv("AGENTBUS_PROVIDERS_STATE", "").strip() or str(BUS_ROOT / "providers_state.json")
# Free-only guard: платные провайдеры недоступны router'у, пока явно не разрешены
# И ВКЛЮЧЕНЫ явной конфигурацией (billing=paid + AGENTBUS_ALLOW_PAID=true).
ALLOW_PAID = os.getenv("AGENTBUS_ALLOW_PAID", "").strip().lower() in {"1", "true", "yes", "on"}


def _tool_path(env_name: str, exe_names: tuple[str, ...], prefs: tuple[str, ...] = ()) -> str:
    """Путь внешнего инструмента: env -> PATH (which) -> известные места.
    Путь НЕ хардкодится в логике — только env или автопоиск."""
    v = os.getenv(env_name, "").strip()
    if v:
        return v
    from shutil import which
    for name in exe_names:
        hit = which(name)
        if hit:
            return hit
    for p in prefs:
        if p and Path(p).is_file():
            return p
    return ""


AIDER_PATH = _tool_path("AIDER_PATH", ("aider.exe", "aider"))
OPENCODE_PATH = _tool_path("OPENCODE_PATH", ("opencode.exe", "opencode"))
AIDER_PYTHON = _tool_path("AIDER_PYTHON", ("python.exe", "python")) or sys.executable
OLLAMA_PATH = _tool_path("OLLAMA_PATH", ("ollama.exe", "ollama"))
AIDER_MODEL = os.getenv("AIDER_MODEL", "ollama_chat/qwen2.5-coder:7b")
OPENCODE_ENABLED = os.getenv("OPENCODE_ENABLED", "").strip().lower() in {"1","true","yes","on"}

# --- Health / scoring ---
HEALTH_BASE_COOLDOWN = max(10, _int("AGENTBUS_HEALTH_BASE_COOLDOWN", 120))
HEALTH_CIRCUIT_LIMIT = max(1, _int("AGENTBUS_HEALTH_CIRCUIT_LIMIT", 3))
HEALTH_SUCCESS_WEIGHT = _float("AGENTBUS_HEALTH_SUCCESS_WEIGHT", 1.0)
HEALTH_SPEED_WEIGHT = _float("AGENTBUS_HEALTH_SPEED_WEIGHT", 1.0)
HEALTH_AVAIL_WEIGHT = _float("AGENTBUS_HEALTH_AVAIL_WEIGHT", 2.0)
HEALTH_FIT_WEIGHT = _float("AGENTBUS_HEALTH_FIT_WEIGHT", 1.0)
HEALTH_FAIL_PENALTY = _float("AGENTBUS_HEALTH_FAIL_PENALTY", 0.5)
# Персистентное состояние воркеров (переживает рестарт диспетчера).
WORKERS_STATE_FILE = os.getenv("AGENTBUS_WORKERS_STATE", "").strip() or str(BUS_ROOT / "workers_state.json")

# --- Adaptive ranker (v3, надстройка над health/score) ---
# RANKER_FEEDBACK=0 отключает обучаемую поправку к score (чистый health).
RANKER_FEEDBACK = _flag("AGENTBUS_RANKER_FEEDBACK", True)
# Максимальная поправка ± к базовому score от выученных метрик.
RANKER_BIAS_LIMIT = max(0.0, _float("AGENTBUS_RANKER_BIAS_LIMIT", 0.5))
# Персистентное состояние профилей исполнителей (обучаемые метрики).
RANKER_STATE_FILE = os.getenv("AGENTBUS_RANKER_STATE", "").strip() or str(BUS_ROOT / "ranker_state.json")

# --- Dynamic pool (v3) ---
# AGENTBUS_USE_DYNAMIC=1: реально добавлять новых воркеров из доступных free/local
# провайдеров в активный пул. По умолчанию выключено — провайдеры и так выключены,
# а подключение foreign (openai_compatible) требует env для base_url/api_key.
# Без флага новые воркеры НЕ создаются (только наблюдаемость пула).
USE_DYNAMIC = _flag("AGENTBUS_USE_DYNAMIC", False)

# --- Retry / backoff (self-contained scheduler) ---
RETRY_DELAY_SECONDS = max(5, _int("AGENTBUS_RETRY_DELAY_SECONDS", 60))
# Minimal hold for a task after a worker failed it (avoid retry with the same failing worker instantly)
FALLBACK_MIN_DELAY = max(0, _int("AGENTBUS_FALLBACK_MIN_DELAY", 20))

# --- Task routing by complexity ---
# complexity 1..5; 1-2 -> local, 3 -> any, 4-5 -> strongest available
COMPLEXITY_LOCAL_MAX = _int("AGENTBUS_COMPLEXITY_LOCAL_MAX", 2)

# --- Git transactions / repair ---
GIT_ENABLED = _flag("AGENTBUS_GIT", True)
REPAIR_ENABLED = _flag("AGENTBUS_REPAIR", True)
REPAIR_MAX_ATTEMPTS = _int("AGENTBUS_REPAIR_MAX_ATTEMPTS", 3)
# Мусор, который НЕ считается «изменением задачи» при commit/rollback:
# никогда не коммитим и не откатываем эти пути (gitignore уже исключает часть).
GIT_IGNORE_EXTRA = tuple(
    x.strip() for x in os.getenv(
        "AGENTBUS_GIT_IGNORE",
        "__pycache__/,*.pyc,.pytest_cache/,*.aider*,*.aider.*-a,*.orig,*.rej,.tmp/,*.tmp",
    ).split(",") if x.strip()
)

# --- Autonomy / night mode ---
AUTOPILOT = os.getenv("AGENTBUS_AUTOPILOT", "off").strip().lower()  # off | on | night
NIGHT_START = os.getenv("AGENTBUS_NIGHT_START", "02:00")
NIGHT_END = os.getenv("AGENTBUS_NIGHT_END", "02:00")  # same == any time
REPORT_DIR = CHANNELS_ROOT / DEFAULT_CHANNEL / "logs"
LOG_ROOT = REPORT_DIR
