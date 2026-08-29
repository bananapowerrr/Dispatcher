# -*- coding: utf-8 -*-
"""
AgentBus Dispatcher v1.0
=======================
Рефакторинг: каналы gpt/grok/gemini, Supabase (GPT-архитектор),
Aider / OpenCode, rate-limit → deferred, pip/pytest verify.

Шина:  channels/gpt/{incoming,processing,done,errors,deferred,logs}
Секреты: .env (SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
Проект:  prediction-analyzer → D:\\Workspace\\Prediction-Analyzer

Запуск:  python dispatcher.py
"""
from __future__ import annotations

import datetime
import json
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Dict, List, Optional, Tuple

VERSION = "1.0"

# ========================= ПУТИ =========================
DRIVE = r"G:\Мой диск\AgentBus"
OPENCODE = r"D:\Progs\opencode.exe"
AIDER = r"C:\Users\user\AppData\Local\Programs\Python\Python312\Scripts\aider.exe"
GIT_EXE = r"C:\Program Files\Git\cmd\git.exe"
PYTHON_EXE = sys.executable

# --- channels bus (gpt = primary / Supabase) ---
CHANNELS_ROOT = os.path.join(DRIVE, "channels")
ARCHIVE_DIR = os.path.join(DRIVE, "archive")
CORE_DIR = os.path.join(DRIVE, "core")
CHANNEL_NAMES = ("gpt", "grok", "gemini")
DEFAULT_CHANNEL = "gpt"

def channel_paths(name: str) -> dict:
    base = os.path.join(CHANNELS_ROOT, name)
    return {
        "root": base,
        "incoming": os.path.join(base, "incoming"),
        "processing": os.path.join(base, "processing"),
        "done": os.path.join(base, "done"),
        "errors": os.path.join(base, "errors"),
        "deferred": os.path.join(base, "deferred"),
        "logs": os.path.join(base, "logs"),
    }

def ensure_channel_dirs() -> None:
    for n in CHANNEL_NAMES:
        for path in channel_paths(n).values():
            os.makedirs(path, exist_ok=True)
    os.makedirs(ARCHIVE_DIR, exist_ok=True)
    os.makedirs(CORE_DIR, exist_ok=True)

_ch = channel_paths(DEFAULT_CHANNEL)
INCOMING = _ch["incoming"]
PROCESSING = _ch["processing"]
DONE = _ch["done"]
ERRORS = _ch["errors"]
DEFERRED = _ch["deferred"]
LOGS = _ch["logs"]
PROJECTS_ROOT = os.path.join(DRIVE, "projects")
GEMINI_ARCHIVE = os.path.join(CHANNELS_ROOT, "gemini", "logs")
RATE_LIMIT_STATE = os.path.join(DRIVE, "rate_limit_until.json")

# ========================= .ENV LOADER =========================
def _parse_dotenv_line(line: str) -> Optional[Tuple[str, str]]:
    line = line.strip()
    if not line or line.startswith("#"):
        return None
    if line.startswith("export "):
        line = line[7:].lstrip()
    if "=" not in line:
        return None
    key, value = line.split("=", 1)
    key = key.strip()
    value = value.strip()
    if not key:
        return None
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        value = value[1:-1]
    else:
        value = re.sub(r"\s+#.*$", "", value).strip()
    return key, value

def load_dotenv() -> Optional[str]:
    """Загружает .env без python-dotenv. Системные переменные приоритетнее."""
    candidates: List[str] = []
    explicit = os.getenv("AGENTBUS_ENV_FILE", "").strip()
    if explicit:
        candidates.append(explicit)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    candidates.extend([
        os.path.join(script_dir, ".env"),
        os.path.join(os.getcwd(), ".env"),
        os.path.join(DRIVE, ".env"),
    ])
    seen = set()
    for path in candidates:
        path = os.path.abspath(path)
        if path in seen or not os.path.isfile(path):
            continue
        seen.add(path)
        try:
            with open(path, "r", encoding="utf-8-sig") as fh:
                for raw in fh:
                    item = _parse_dotenv_line(raw)
                    if item:
                        key, value = item
                        os.environ.setdefault(key, value)
            return path
        except OSError:
            continue
    return None

ENV_FILE_LOADED = load_dotenv()

# ========================= SUPABASE =========================
SUPABASE_ENABLED = os.getenv("SUPABASE_ENABLED", "true").strip().lower() not in {"0", "false", "no", "off"}
SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
SUPABASE_SERVICE_ROLE_KEY = (
    os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    or os.getenv("SUPABASE_SERVICE_ROLE", "").strip()
    or os.getenv("SUPABASE_KEY", "").strip()
)
SUPABASE_POLL_SEC = max(2, int(os.getenv("SUPABASE_POLL_SEC", "5")))
SUPABASE_TIMEOUT = max(5, int(os.getenv("SUPABASE_TIMEOUT", "30")))
SUPABASE_STALE_SEC = max(60, int(os.getenv("SUPABASE_STALE_SEC", "300")))
SUPABASE_MAX_ATTEMPTS = max(1, int(os.getenv("SUPABASE_MAX_ATTEMPTS", "3")))
SUPABASE_TOUCH_SEC = max(20, int(os.getenv("SUPABASE_TOUCH_SEC", "45")))

WORKER_ID = (
    os.getenv("AGENTBUS_WORKER_ID", "").strip()
    or f"{socket.gethostname()}-{os.getpid()}-{datetime.datetime.now().strftime('%Y%m%d-%H%M%S')}"
)

# ========================= GEMINI =========================
GEMINI_DOCS_ENABLED = os.getenv("GEMINI_DOCS_ENABLED", "0").strip().lower() in {"1", "true", "yes", "on"}
GEMINI_SOURCE_FOLDER_ID = None
GEMINI_PROCESSED_FOLDER = "GeminiProcessed"
GEMINI_CREDENTIALS = os.path.join(DRIVE, "credentials", "credentials.json")
GEMINI_TOKEN = os.path.join(DRIVE, "credentials", "token.json")
GEMINI_POLL_SEC = 60

# ========================= ПРОЕКТЫ =========================
def _first_existing(*candidates: str) -> str:
    """Первый существующий путь или первый кандидат (для BOOT-предупреждения)."""
    for c in candidates:
        c = (c or "").strip().strip('"').strip("'")
        if c and os.path.isdir(c):
            return c
    return (candidates[0] if candidates else "") or ""

# Пути можно переопределить в .env:
#   PROJECT_PREDICTION_ANALYZER=D:\path\to\repo
#   PROJECT_DISPATCHER=D:\path\to\Dispatcher
_pa = os.getenv("PROJECT_PREDICTION_ANALYZER", "").strip()
_disp = os.getenv("PROJECT_DISPATCHER", "").strip()
_PA_PATH = _first_existing(
    _pa,
    r"D:\Workspace\Prediction-Analyzer",
    r"D:\Workspace\desktop-tutorial",
    r"D:\Workspace\Prediction_Analyzer",
    r"C:\Workspace\Prediction-Analyzer",
    r"C:\Workspace\desktop-tutorial",
)
_DISP_PATH = _first_existing(
    _disp,
    r"D:\Workspace\Dispatcher",
    r"C:\Workspace\Dispatcher",
)

PROJECTS = {
    "prediction-analyzer": {
        "path": _PA_PATH,
        "repo": "bananapowerrr/Prediction-Analyzer",
    },
    "desktop-tutorial": {  # алиас старого имени
        "path": _PA_PATH,
        "repo": "bananapowerrr/Prediction-Analyzer",
    },
    "dispatcher": {
        "path": _DISP_PATH,
        "repo": "bananapowerrr/Dispatcher",
    },
}
DEFAULT_PROJECT = "prediction-analyzer"

# ========================= СЕТЬ =========================
PROXY_URL = os.getenv("AGENTBUS_PROXY_URL", "").strip()

def apply_network_env() -> None:
    if not PROXY_URL:
        return
    for key in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
        os.environ[key] = PROXY_URL
    os.environ.setdefault("NO_PROXY", "localhost,127.0.0.1")

# ========================= НАСТРОЙКИ =========================
MAX_TRIES = 3
GIT_RETRIES = 5
STALE_TIME = 120
GIT_ENABLED = True
CODER_TIMEOUT = 1800
REQUIRE_FILES = True
MIN_PY_BYTES = 20
AIDER_FALLBACK_TO_OPENCODE = True
ALLOW_CLOUD_FALLBACK = True
AIDER_MAX_FILES = 2
DAILY_CLOUD_BUDGET = 999999
CLOUD_USAGE_FILE = os.path.join(DRIVE, "cloud_usage.json")
CIRCUIT_BREAKER_LIMIT = 8
CIRCUIT_SLEEP_SEC = 300
MAX_TASKS_PER_CYCLE = 15
WRITE_SUCCESS_REPORTS = True
REPORT_KEEP = 10
ERRORS_KEEP = 30
CLEANUP_IDLE_SEC = 90
SESSION_KEEP_DAYS = 3

AIDER_MODEL = "ollama_chat/qwen2.5-coder:7b"
AIDER_EXTRA_ARGS = ["--no-auto-commits", "--no-pretty", "--no-stream"]
OPENCODE_MODELS = [
    "opencode/big-pickle",
    "opencode/hy3-free",
    "opencode/ox-alpha-free",
    "opencode/x-preview-f-free",
    "opencode/muse-spark-1.2-contributor-free",
]

SUPPORTED_EXT = (".md", ".txt")
SKIP_TASK_PATTERNS = [
    r"дорожн\w*\s+карт",
    r"мастер[- ]?список",
    r"фаза\s*[0-9]",
    r"phase\s*[0-9]",
    r"сводн\w*\s+таблиц",
    r"техническ\w*\s+задани",
]
BAD_SIGNS = [
    "traceback (most recent call last)",
    "permission denied",
    "отказано в доступе",
    "malformed edit",
    "не удалось",
]
STUB_MARKERS = [
    "TODO: implement", "pass  # stub", "# заглушка", "# placeholder",
    "EXACTLY THIS TEXT", "Здесь должен быть", "NotImplementedError",
    "# insert code", "# implement this", "# auto-created by dispatcher",
]
LIVE_CODE_HINTS = (
    "assert ", "return ", "raise ", "yield ", "await ",
    "class ", "async def ", "print(", "self.",
)
CLARIFY_PHRASES = [
    "please specify", "уточните", "укажите", "please clarify",
    "what changes", "какие изменения", "что именно", "какой файл",
    "какие файлы", "уточни", "provide the file", "provide files",
    "add them to the chat", "no files provided", "which files",
    "files to edit", "add the file", "need the file", "specify the file",
]
INFRA_SIGNS = [
    "has no attribute 'exc'", "0xc0000005", "llama-server process has terminated",
    "GitCommandError", "3221225477", "winerror 5", "отказано в доступе",
]
COMPLEXITY_KEYWORDS = [
    "failover", "blockchain", "rpc", "web3", "state machine",
    "рефактор", "архитектур", "интеграци", "multi-file", "удали все",
    "cleanup", "очист", "рекурсив",
]

ANSI = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")

SESSION_ID = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
SESSION_LOG = os.path.join(LOGS, f"session_{SESSION_ID}.md")
DISPATCHER_LOG = os.path.join(LOGS, "dispatcher.log")

LAST_BEAT = time.time()
FAIL_STREAK = 0
TASKS_DONE_CYCLE = 0
LAST_CLEANUP = 0.0
LAST_SUPABASE_REQUEUE = 0.0
LAST_SUPABASE_TOUCH = 0.0
CLOUD_RATE_LIMIT_UNTIL = 0.0
SUPABASE_COOLDOWN_UNTIL = 0.0
CURRENT_SUPABASE_TASK_ID: Optional[str] = None
SHUTTING_DOWN = False
_last_gemini_poll = 0.0
_last_supabase_poll = 0.0
_repo_tree_cache: Dict[str, Tuple[float, set]] = {}

# ========================= IO / ЛОГИ =========================
def now() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

def _today() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d")

def read(path: str) -> str:
    if not os.path.exists(path):
        return ""
    with open(path, encoding="utf-8", errors="replace") as fh:
        return fh.read()

def write(path: str, text: str) -> None:
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)

def append_log(path: str, line: str) -> None:
    try:
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(path, "a", encoding="utf-8") as fh:
            f.write(line if line.endswith("\n") else line + "\n")
    except Exception:
        pass

def slog(msg: str, also_print: bool = True) -> None:
    append_log(SESSION_LOG, msg)
    append_log(DISPATCHER_LOG, msg)
    if also_print:
        try:
            print(msg.rstrip("\n"))
        except UnicodeEncodeError:
            print(msg.encode("ascii", errors="replace").decode("ascii"))

# ========================= SUPABASE API =========================
def supabase_enabled() -> bool:
    return bool(SUPABASE_ENABLED and SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY)

def _ascii_safe(s) -> str:
    """Убирает не-ASCII символы для HTTP-заголовков urllib."""
    if not isinstance(s, str):
        s = str(s)
    return "".join(c for c in s if ord(c) < 128).strip()

def _safe_supabase_error(body: object) -> str:
    text = body if isinstance(body, str) else json.dumps(body, ensure_ascii=False)
    text = re.sub(
        r"(?i)(authorization|apikey|token|secret)\s*[:=]\s*\S+",
        r"\1=<redacted>",
        text,
    )
    return text[:1000]

def supabase_request(
    method: str,
    path: str,
    payload=None,
    query=None,
    timeout: int = SUPABASE_TIMEOUT,
) -> Tuple[int, Optional[object]]:
    if not supabase_enabled():
        return 0, None
    url = f"{SUPABASE_URL}{path}"
    if query:
        url += "?" + urllib.parse.urlencode(query)
    headers = {
        "apikey": _ascii_safe(SUPABASE_SERVICE_ROLE_KEY),
        "Authorization": "Bearer " + _ascii_safe(SUPABASE_SERVICE_ROLE_KEY),
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": f"AgentBus-Dispatcher/{VERSION}",
        "Prefer": "return=representation",
    }
    data = (
        json.dumps(payload, ensure_ascii=False).encode("utf-8")
        if payload is not None
        else None
    )
    req = urllib.request.Request(
        url,
        data=data,
        headers=headers,
        method=method.upper(),
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return resp.status, (json.loads(body) if body else None)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        try:
            parsed = json.loads(body) if body else None
        except Exception:
            parsed = {"error": body[:1000]}
        return exc.code, parsed
    except Exception as exc:
        return 0, {"error": str(exc)}

def supabase_rpc(name: str, payload: dict) -> Tuple[int, Optional[object]]:
    return supabase_request("POST", f"/rest/v1/rpc/{name}", payload=payload)

def _as_list(value) -> List[str]:
    """Парсит JSON array или Postgres array literal {"a","b"}."""
    if value is None:
        return []
    if isinstance(value, list):
        return [str(x) for x in value if str(x).strip()]
    if not isinstance(value, str):
        return []
    s = value.strip()
    if not s:
        return []
    # Postgres array literal: {"a","b","c"}
    if s.startswith("{") and s.endswith("}"):
        inner = s[1:-1]
        if not inner.strip():
            return []
        parts = []
        for p in re.split(r',', inner):
            p = p.strip().strip('"')
            if p:
                parts.append(p)
        return parts
    # Обычная строка через запятую/точку с запятой/перевод
    return [x.strip() for x in re.split(r"[,;\n]+", s) if x.strip()]

def claim_supabase_task() -> Optional[dict]:
    global SUPABASE_COOLDOWN_UNTIL, _last_supabase_poll
    if not supabase_enabled() or time.time() < SUPABASE_COOLDOWN_UNTIL:
        return None
    if time.time() - _last_supabase_poll < SUPABASE_POLL_SEC:
        return None
    _last_supabase_poll = time.time()
    code, result = supabase_rpc(
        "agentbus_claim_task",
        {"worker_id": WORKER_ID},
    )
    if code == 0:
        slog(f"[{now()}] supabase: connection error: {_safe_supabase_error(result)}")
        SUPABASE_COOLDOWN_UNTIL = time.time() + 30
        return None
    if code not in (200, 201):
        slog(f"[{now()}] supabase: claim HTTP {code}: {_safe_supabase_error(result)}")
        SUPABASE_COOLDOWN_UNTIL = time.time() + (60 if code in (401, 403) else 15)
        return None
    row = None
    if isinstance(result, list):
        row = result[0] if result else None
    elif isinstance(result, dict):
        row = result
    if not isinstance(row, dict) or not row.get("id"):
        return None
    return {
        "id": str(row["id"]),
        "project": row.get("project") or DEFAULT_PROJECT,
        "executor": str(row.get("executor") or "aider").lower(),
        "model": row.get("model") or "",
        "files": _as_list(row.get("files")),
        "message": row.get("message") or "",
        "verify": _as_list(row.get("verify")),
        "run": _as_list(row.get("run")),
        "allow_no_files": bool(row.get("allow_no_files")),
        "author": row.get("author") or "",
        "source": row.get("source") or "supabase",
        "source_id": row.get("source_id") or "",
        "supabase_id": str(row["id"]),
    }

def touch_supabase_task(task_id: str) -> bool:
    if not supabase_enabled() or not task_id:
        return False
    ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
    code, body = supabase_request(
        "PATCH",
        "/rest/v1/agentbus_tasks",
        payload={"claimed_at": ts, "updated_at": ts},
        query={
            "id": f"eq.{task_id}",
            "status": "eq.CLAIMED",
            "worker_id": f"eq.{WORKER_ID}",
        },
    )
    if code not in (200, 204):
        slog(f"[{now()}] supabase: touch HTTP {code} for {task_id}: {_safe_supabase_error(body)}")
        return False
    return True

def finish_supabase_task(task_id: str, result: str) -> bool:
    if not supabase_enabled() or not task_id:
        return False
    code, body = supabase_rpc(
        "agentbus_finish_task",
        {
            "task_id": str(task_id),
            "worker_id": WORKER_ID,
            "status": "DONE",
            "result": (result or "")[:5000],
            "error": None,
        },
    )
    if code not in (200, 201, 204):
        slog(f"[{now()}] supabase: finish HTTP {code}: {_safe_supabase_error(body)}")
        return False
    return True

def fail_supabase_task(task_id: str, error: str) -> bool:
    if not supabase_enabled() or not task_id:
        return False
    code, body = supabase_rpc(
        "agentbus_finish_task",
        {
            "task_id": str(task_id),
            "worker_id": WORKER_ID,
            "status": "ERROR",
            "result": None,
            "error": (error or "")[:5000],
        },
    )
    if code not in (200, 201, 204):
        slog(f"[{now()}] supabase: fail HTTP {code}: {_safe_supabase_error(body)}")
        return False
    return True

def requeue_current_supabase_task(task_id: str) -> bool:
    """Вернуть нашу CLAIMED задачу в PENDING при graceful shutdown."""
    if not supabase_enabled() or not task_id:
        return False
    ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
    code, body = supabase_request(
        "PATCH",
        "/rest/v1/agentbus_tasks",
        payload={
            "status": "PENDING",
            "worker_id": None,
            "claimed_by": None,
            "claimed_at": None,
            "updated_at": ts,
        },
        query={
            "id": f"eq.{task_id}",
            "status": "eq.CLAIMED",
            "worker_id": f"eq.{WORKER_ID}",
        },
    )
    if code not in (200, 204):
        slog(f"[{now()}] supabase: shutdown requeue HTTP {code}: {_safe_supabase_error(body)}")
        return False
    slog(f"[{now()}] supabase: shutdown requeue OK: {task_id}")
    return True

def requeue_stale_supabase_tasks() -> int:
    global LAST_SUPABASE_REQUEUE
    if not supabase_enabled():
        return 0
    if time.time() - LAST_SUPABASE_REQUEUE < 30:
        return 0
    LAST_SUPABASE_REQUEUE = time.time()
    code, body = supabase_rpc(
        "agentbus_requeue_stale",
        {"stale_seconds": SUPABASE_STALE_SEC, "max_attempts": SUPABASE_MAX_ATTEMPTS},
    )
    if code not in (200, 201):
        if code:
            slog(f"[{now()}] supabase: requeue HTTP {code}: {_safe_supabase_error(body)}")
        return 0
    if isinstance(body, dict):
        n = int(body.get("requeued", 0) or 0)
        failed = int(body.get("failed", 0) or 0)
        if n or failed:
            slog(f"[{now()}] supabase: stale requeue={n}, max-attempts-error={failed}")
        return n
    return 0

def supabase_heartbeat() -> None:
    global LAST_SUPABASE_TOUCH
    if not CURRENT_SUPABASE_TASK_ID:
        return
    if time.time() - LAST_SUPABASE_TOUCH < SUPABASE_TOUCH_SEC:
        return
    LAST_SUPABASE_TOUCH = time.time()
    touch_supabase_task(CURRENT_SUPABASE_TASK_ID)

# ========================= ОКРУЖЕНИЕ =========================
def base_env() -> Dict[str, str]:
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env["TERM"] = "dumb"
    env["NO_COLOR"] = "1"
    env["OLLAMA_API_BASE"] = env.get("OLLAMA_API_BASE") or "http://127.0.0.1:11434"
    env["OLLAMA_NUM_CTX"] = env.get("OLLAMA_NUM_CTX") or "4096"
    env["GCM_INTERACTIVE"] = "0"
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GIT_ASKPASS"] = ""
    env["GIT_PYTHON_REFRESH"] = "quiet"
    env["LC_ALL"] = "C.UTF-8"
    env["LANG"] = "C.UTF-8"
    return env

# ========================= БЮДЖЕТ ОБЛАКА =========================
def load_cloud_usage() -> dict:
    try:
        data = json.loads(read(CLOUD_USAGE_FILE) or "{}")
    except Exception:
        data = {}
    if data.get("date") != _today():
        return {"date": _today(), "count": 0}
    return data

def note_cloud_use(n: int = 1) -> None:
    data = load_cloud_usage()
    data["count"] = int(data.get("count", 0)) + n
    data["date"] = _today()
    write(CLOUD_USAGE_FILE, json.dumps(data, ensure_ascii=False, indent=2))

def cloud_budget_left() -> int:
    return max(0, DAILY_CLOUD_BUDGET - int(load_cloud_usage().get("count", 0)))

# ========================= ДЕРЕВО РЕПЫ / ФАЙЛЫ =========================
def list_repo_files(project_path: str) -> set:
    global _repo_tree_cache
    ts = time.time()
    cached = _repo_tree_cache.get(project_path)
    if cached and ts - cached[0] < 120:
        return cached[1]
    files = set()
    if not os.path.isdir(project_path):
        return files
    skip_dirs = {".git", "__pycache__", ".vibe", ".aider", "node_modules", ".venv", "venv"}
    for root, dirs, names in os.walk(project_path):
        dirs[:] = [d for d in dirs if d not in skip_dirs and not d.startswith(".")]
        rel_root = os.path.relpath(root, project_path)
        for name in names:
            if name.startswith(".") and name not in (".gitignore", ".env.example", ".env.sample"):
                continue
            rel = name if rel_root == "." else os.path.join(rel_root, name).replace("\\", "/")
            files.add(rel)
            files.add(rel.replace("/", "\\"))
    _repo_tree_cache[project_path] = (ts, files)
    return files

def path_allowed(project_path: str, rel: str, allow_create: bool = True) -> bool:
    rel_n = rel.strip().replace("\\", "/").lstrip("./")
    if not rel_n or rel_n in (".", "..") or ".." in rel_n.split("/"):
        return False
    if rel_n.startswith("/") or (len(rel_n) > 1 and rel_n[1] == ":"):
        return False
    root = os.path.normpath(project_path)
    abs_path = os.path.normpath(os.path.join(root, rel_n.replace("/", os.sep)))
    if os.path.commonpath([root, abs_path]) != root:
        return False
    if os.path.exists(abs_path):
        return True
    allowed_ext = (".py", ".md", ".txt", ".json", ".yml", ".yaml", ".toml", ".ini", ".cfg")
    allowed_names = {".gitignore", ".env.example", ".env.sample", ".editorconfig", ".dockerignore"}
    base = rel_n.split("/")[-1]
    if allow_create and (rel_n.endswith(allowed_ext) or base in allowed_names):
        return True
    tree = list_repo_files(project_path)
    return rel_n in tree or rel_n.replace("/", "\\") in tree

def ensure_target_files(project_path: str, files: List[str]) -> List[str]:
    created: List[str] = []
    root = os.path.normpath(project_path)
    for f in files:
        rel_n = f.strip().replace("\\", "/").lstrip("./")
        if not rel_n or ".." in rel_n.split("/"):
            continue
        abs_f = os.path.normpath(os.path.join(root, rel_n.replace("/", os.sep)))
        if os.path.commonpath([root, abs_f]) != root:
            continue
        os.makedirs(os.path.dirname(abs_f), exist_ok=True)
        if not os.path.exists(abs_f):
            with open(abs_f, "w", encoding="utf-8") as fh:
                if abs_f.endswith(".py"):
                    fh.write("# создано диспетчером для привязки Aider\n")
                else:
                    fh.write("")
            created.append(rel_n)
            slog(f"[{now()}] предсоздание: {rel_n}")
    _repo_tree_cache.pop(project_path, None)
    return created

# ========================= РАЗБОР ЗАДАЧИ =========================
def parse_meta(text: str) -> dict:
    meta = {
        "project": DEFAULT_PROJECT,
        "executor": "aider",
        "model": "",
        "files": [],
        "message": "",
        "verify": [],
        "run": [],
        "allow_no_files": False,
        "author": "",
        "body_tasks": [],
    }
    mode = None
    message_lines: List[str] = []
    for line in text.splitlines():
        s = line.strip()
        low = s.lower()
        if low.startswith("project:"):
            meta["project"] = s.split(":", 1)[1].strip() or DEFAULT_PROJECT
            mode = None
            continue
        if low.startswith("executor:"):
            meta["executor"] = s.split(":", 1)[1].strip().lower() or "aider"
            mode = None
            continue
        if low.startswith("model:"):
            meta["model"] = s.split(":", 1)[1].strip()
            mode = None
            continue
        if low.startswith("author:"):
            meta["author"] = s.split(":", 1)[1].strip()
            mode = None
            continue
        if low.startswith("files:"):
            raw = s.split(":", 1)[1].strip()
            meta["files"] = [p for p in re.split(r"[,;\s]+", raw) if p and p != "."]
            mode = None
            continue
        if low.startswith("allow_no_files:"):
            meta["allow_no_files"] = s.split(":", 1)[1].strip().lower() in ("1", "true", "yes", "да")
            mode = None
            continue
        if low.startswith("message:"):
            rest = s.split(":", 1)[1].strip()
            mode = "message"
            if rest and rest != "|":
                message_lines.append(rest)
            continue
        if low.startswith("verify:"):
            mode = "verify"
            continue
        if low.startswith("run:"):
            rest = s.split(":", 1)[1].strip()
            mode = "run"
            if rest and rest != "|":
                meta["run"].append(rest)
            continue
        m = re.match(r"^[\s\-\*•]*\[([ x~])\]\s*(.+)$", s)
        if m:
            mode = None
            if m.group(1) == " ":
                meta["body_tasks"].append(m.group(2).strip())
            continue
        if mode == "message":
            if low.startswith(("project:", "executor:", "files:", "model:", "verify:", "run:")):
                mode = None
            else:
                message_lines.append(line.rstrip())
            continue
        if mode == "verify" and s.startswith("-"):
            meta["verify"].append(s.lstrip("- ").strip())
            continue
        if mode == "verify" and not s:
            mode = None
            continue
        if mode == "run" and s.startswith("-"):
            meta["run"].append(s.lstrip("- ").strip())
            continue
        if mode == "run" and s:
            meta["run"].append(s)
            continue
    meta["message"] = "\n".join(message_lines).strip()
    return meta

def extract_tasks(meta: dict, raw: str) -> List[str]:
    if meta.get("body_tasks"):
        return list(meta["body_tasks"])
    if meta.get("message"):
        return [meta["message"]]
    skip = (
        "project:", "executor:", "model:", "files:", "message:",
        "verify:", "run:", "allow_no_files:", "author:", "created:",
        "source_", "# task", "# задача", "---"
    )
    lines = []
    for line in raw.splitlines():
        low = line.strip().lower()
        if any(low.startswith(p) for p in skip):
            continue
        if line.strip().startswith("#") and len(line.strip()) < 40:
            continue
        lines.append(line)
    body = "\n".join(lines).strip()
    return [body] if body else []

def looks_like_roadmap_noise(text: str) -> bool:
    if not text or len(text.strip()) < 20:
        return True
    low = text.lower()
    hits = sum(1 for p in SKIP_TASK_PATTERNS if re.search(p, low))
    verbs = ["создай", "добавь", "напиши", "реализуй", "исправь", "удали",
             "create", "add", "write", "implement", "fix", "delete", "update"]
    has_verb = any(v in low for v in verbs)
    return (hits >= 1 and not has_verb) or (hits >= 2 and len(text) > 500)

def is_complex_task(text: str, files: List[str]) -> bool:
    low = (text or "").lower()
    hits = sum(1 for kw in COMPLEXITY_KEYWORDS if kw in low)
    return (
        hits >= 2
        or len(files) > AIDER_MAX_FILES
        or any(k in low for k in ("удали все", "cleanup", "очист", "рекурсив"))
    )

# ========================= ЗАПУСК КОМАНД =========================
def run_cmd(
    args: List[str],
    cwd: str,
    timeout: Optional[int] = None,
    env: Optional[dict] = None,
    retries: int = 1,
) -> Tuple[int, str]:
    timeout = timeout or CODER_TIMEOUT
    env = env or base_env()
    if args and args[0].lower() in ("git", "git.exe") and os.path.exists(GIT_EXE):
        args = [GIT_EXE] + list(args[1:])
    last_out = ""
    for attempt in range(1, max(1, retries) + 1):
        try:
            proc = subprocess.Popen(
                args, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace", env=env,
            )
            timer = threading.Timer(timeout, proc.kill)
            timer.start()
            lines = []
            try:
                assert proc.stdout is not None
                for line in proc.stdout:
                    clean = ANSI.sub("", line).rstrip()
                    if clean:
                        try:
                            print(f"    | {clean[:200]}")
                        except Exception:
                            pass
                    lines.append(line)
            finally:
                timer.cancel()
                proc.wait()
            code = proc.returncode or 0
            last_out = "".join(lines)
            low = last_out.lower()
            access = code != 0 and any(
                x in low for x in ("winerror 5", "отказано в доступе", "access is denied")
            )
            if access and attempt < retries:
                slog(f"[{now()}] отказ в доступе, повтор {attempt + 1}/{retries}: {args[0]}")
                time.sleep(1.5 * attempt)
                continue
            return code, last_out
        except OSError as exc:
            last_out = f"ошибка запуска: {exc}"
            if attempt < retries:
                slog(f"[{now()}] ошибка ОС, повтор {attempt + 1}/{retries}: {exc}")
                time.sleep(1.5 * attempt)
                continue
            return 1, last_out
        except Exception as exc:
            return 1, f"ошибка запуска: {exc}"
    return 1, last_out

# ========================= ИСПОЛНИТЕЛИ =========================
def run_aider(prompt: str, files: List[str], project_path: str) -> Tuple[int, str]:
    ensure_target_files(project_path, files)
    cmd = [AIDER, "--yes", "--model", AIDER_MODEL] + AIDER_EXTRA_ARGS
    count = 0
    for f in files:
        abs_f = os.path.join(project_path, f.replace("/", os.sep))
        if os.path.isfile(abs_f):
            cmd += ["--file", abs_f]
            count += 1
    if not count:
        return 1, "НЕТ_ФАЙЛОВ_AIDER: нет целей --file после предсоздания; укажите FILES:"
    cmd += ["--message", prompt]
    slog(f"[{now()}] aider --file ×{count}")
    return run_cmd(cmd, project_path, env=base_env())

def run_opencode(prompt: str, project_path: str, model: str = "") -> Tuple[int, str]:
    """Запуск OpenCode. При rate-limit — СРАЗУ стоп, без перебора моделей."""
    until = load_rate_limit_until()
    if until and time.time() < until:
        left = int(until - time.time())
        msg = f"облачный лимит активен ещё {left}с — OpenCode не вызываем"
        slog(f"[{now()}] {msg}")
        return 429, msg

    models = ([model] if model else []) + [m for m in OPENCODE_MODELS if m != model]
    last_code, last_out = 1, ""
    for m in models:
        if cloud_budget_left() <= 0 and "free" in m:
            continue
        slog(f"[{now()}] OpenCode, модель: {m}")
        code, out = run_cmd([OPENCODE, "run", "--model", m, prompt], project_path, env=base_env())
        note_cloud_use(1)
        last_code, last_out = code, out

        # Лимит / 429 — не тратим время на остальные модели
        if is_rate_limit_output(out) or code == 429:
            wait_sec = parse_rate_limit_seconds(out, default_sec=3600)
            save_rate_limit_until(time.time() + wait_sec)
            slog(f"[{now()}] ЛИМИТ OpenCode на модели {m}. Пауза {wait_sec}с. Остальные модели не трогаем.")
            return 429, out

        low = out.lower()
        if code == 0 and not any(s in low for s in BAD_SIGNS):
            if not any(x in low for x in ("forbidden", "model not found")):
                return code, out
        # Модель недоступна / не найдена — можно попробовать следующую
        if any(x in low for x in ("model not found", "forbidden", "unknown model", "not available")):
            slog(f"[{now()}] модель {m} недоступна → следующая")
            continue
        slog(f"[{now()}] модель {m} не справилась (код {code}) → следующая")
    return last_code, last_out

def is_infra_fail(output: str) -> bool:
    return any(s in (output or "").lower() for s in INFRA_SIGNS)

def is_clarify(output: str) -> bool:
    low = (output or "").lower()
    return (
        any(p in low for p in CLARIFY_PHRASES)
        or "aider_no_files" in low
        or "нет_файлов_aider" in low
    )

def is_code_ok(code: int, output: str) -> bool:
    if is_clarify(output) or is_infra_fail(output):
        return False
    low = (output or "").lower()
    if any(s in low for s in BAD_SIGNS):
        return False
    return (
        code == 0
        or any(x in low for x in ("applied edit", "wrote ", "updated ", "записан"))
    )

# ========================= ПРОВЕРКА / RUN =========================
def snapshot_mtimes(project_path: str, files: List[str]) -> Dict[str, float]:
    result = {}
    for f in files:
        p = os.path.join(project_path, f.replace("/", os.sep))
        try:
            result[f] = os.path.getmtime(p)
        except OSError:
            result[f] = 0.0
    return result

def files_changed(project_path: str, files: List[str], before: Dict[str, float]) -> bool:
    if not files:
        _, out = run_cmd([GIT_EXE, "status", "--porcelain"], project_path, 30, retries=2)
        return bool(out.strip())
    for f in files:
        p = os.path.join(project_path, f.replace("/", os.sep))
        if os.path.exists(p) and os.path.getmtime(p) > before.get(f, 0):
            return True
    _, out = run_cmd([GIT_EXE, "status", "--porcelain"], project_path, 30, retries=2)
    return bool(out.strip())

def has_live_code(text: str) -> bool:
    low = text.lower()
    return "def " in low or any(h in low for h in LIVE_CODE_HINTS)

def stub_heavy(project_path: str, files: List[str]) -> bool:
    for f in files:
        if not f.endswith(".py"):
            continue
        p = os.path.join(project_path, f.replace("/", os.sep))
        if not os.path.isfile(p):
            continue
        body = "\n".join(
            ln for ln in read(p).splitlines()
            if "создано диспетчером" not in ln and "auto-created by dispatcher" not in ln
        )
        if has_live_code(body):
            hits = sum(1 for m in STUB_MARKERS if m.lower() in body.lower())
            if hits >= 3:
                return True
        else:
            if len(body.strip()) < MIN_PY_BYTES:
                return True
            hits = sum(1 for m in STUB_MARKERS if m.lower() in body.lower())
            if hits >= 2 or (hits >= 1 and body.count("\n") < 15 and "NotImplementedError" in body):
                return True
    return False

def py_compile_files(project_path: str, files: List[str]) -> Tuple[bool, str]:
    targets = [f for f in files if f.endswith(".py")]
    if not targets:
        _, out = run_cmd([GIT_EXE, "status", "--porcelain"], project_path, 30, retries=2)
        targets = [
            line[3:].strip().replace('"', "")
            for line in out.splitlines()
            if len(line) > 3 and line[3:].strip().endswith(".py")
        ]
    errors = []
    for f in targets:
        p = os.path.join(project_path, f.replace("/", os.sep))
        if not os.path.isfile(p):
            errors.append(f"НЕТ ФАЙЛА: {f}")
            continue
        code, out = run_cmd(
            [sys.executable or "python", "-m", "py_compile", p],
            project_path, 60, env=base_env(), retries=3,
        )
        if code != 0:
            errors.append(f"ОШИБКА_КОМПИЛЯЦИИ: {f}\n{out[-500:]}")
    return not errors, "\n".join(errors)

def verify_task(project_path: str, meta: dict, files: List[str]) -> Tuple[bool, str]:
    """Проверки: pip requirements → py_compile → stubs → VERIFY (pytest и т.д.)."""
    notes = []
    for f in files:
        if not os.path.exists(os.path.join(project_path, f.replace("/", os.sep))):
            notes.append(f"НЕТ ФАЙЛА: {f}")
    if notes and not meta.get("allow_no_files") and any(f.endswith(".py") for f in files):
        return False, "\n".join(notes)

    # 1) requirements.txt → pip install (тот же Python, что диспетчер/Aider)
    req_path = os.path.join(project_path, "requirements.txt")
    need_pip = os.path.isfile(req_path)
    verify_list = list(meta.get("verify") or [])
    run_list = list(meta.get("run") or [])
    wants_pytest = any("pytest" in (x or "").lower() for x in verify_list + run_list)
    # pip только если явно pip_install / VERIFY с pytest / AUTO_PIP_INSTALL=1
    auto_pip = os.environ.get("AUTO_PIP_INSTALL", "0").strip().lower() in {"1", "true", "yes"}
    if need_pip and (wants_pytest or meta.get("pip_install") or auto_pip):
        slog(f"[{now()}] установка зависимостей: requirements.txt")
        code, out = run_cmd(
            [sys.executable or "python", "-m", "pip", "install", "-r", "requirements.txt", "-q"],
            project_path, 600, env=base_env(), retries=1,
        )
        if code != 0:
            return False, f"PIP_INSTALL_FAIL:\n{(out or '')[-1500:]}"
        slog(f"[{now()}] pip install OK")

    # 2) py_compile
    ok, msg = py_compile_files(project_path, files)
    if not ok:
        return False, msg
    if stub_heavy(project_path, files):
        return False, "МНОГО_ЗАГЛУШЕК"

    # 3) VERIFY lines: exists / pytest ...
    for v in verify_list:
        v = (v or "").strip()
        if not v:
            continue
        m = re.match(r"^(\S+)\s+(?:exists|существует)", v, re.I)
        if m:
            if not os.path.exists(os.path.join(project_path, m.group(1).replace("/", os.sep))):
                return False, f"ПРОВЕРКА: {m.group(1)} не найден"
            continue
        if "pytest" in v.lower():
            # "pytest -q" или "python -m pytest -q"
            cmd = v
            if not cmd.lower().startswith("python"):
                cmd = f'"{sys.executable}" -m pytest ' + re.sub(r"^pytest\s*", "", v, flags=re.I)
            else:
                cmd = normalize_run_command(cmd)
            slog(f"[{now()}] VERIFY pytest: {cmd}")
            try:
                proc = subprocess.run(
                    cmd, cwd=project_path, shell=True, capture_output=True, text=True,
                    encoding="utf-8", errors="replace", timeout=600, env=base_env(),
                )
                out = (proc.stdout or "") + "\n" + (proc.stderr or "")
                if proc.returncode != 0:
                    return False, f"PYTEST_FAIL ({proc.returncode}):\n{out[-2000:]}"
                slog(f"[{now()}] pytest OK")
            except subprocess.TimeoutExpired:
                return False, "pytest timeout"
            continue
        # произвольная команда в VERIFY
        if v.lower().startswith(("python", "py ", "pip ")):
            cmd = normalize_run_command(v)
            slog(f"[{now()}] VERIFY: {cmd}")
            code, out = run_cmd(cmd if isinstance(cmd, list) else cmd, project_path, 300, env=base_env(), retries=1)
            # run_cmd expects list - use shell via subprocess
            try:
                proc = subprocess.run(
                    cmd, cwd=project_path, shell=True, capture_output=True, text=True,
                    encoding="utf-8", errors="replace", timeout=300, env=base_env(),
                )
                if proc.returncode != 0:
                    return False, f"VERIFY_FAIL: {v}\n{((proc.stdout or '')+(proc.stderr or ''))[-1500:]}"
            except Exception as e:
                return False, f"VERIFY_FAIL: {e}"
    return True, "ok"

def normalize_run_command(cmd: str) -> str:
    py = sys.executable or "python"
    py_q = f'"{py}"' if " " in py and not py.startswith('"') else py
    return re.sub(
        r"(^|[;&|\s])(python3?|py)(?=\s|$)",
        lambda m: m.group(1) + py_q,
        cmd, count=1, flags=re.I,
    )

def run_task_commands(project_path: str, commands: List[str]) -> Tuple[bool, str]:
    logs = []
    for cmd in commands[:5]:
        cmd = normalize_run_command(cmd.strip())
        if not cmd:
            continue
        low = cmd.lower()
        if any(x in low for x in ("rm -rf /", "format c:", "del /f /s", "shutdown", "mkfs")):
            return False, f"ЗАБЛОКИРОВАНО: {cmd}"
        slog(f"[{now()}] RUN: {cmd}")
        try:
            proc = subprocess.run(
                cmd, cwd=project_path, shell=True, capture_output=True,
                text=True, encoding="utf-8", errors="replace", timeout=120, env=base_env(),
            )
            chunk = (proc.stdout or "") + (proc.stderr or "")
            logs.append(f"$ {cmd}\nкод={proc.returncode}\n{chunk[-1500:]}")
            if proc.returncode != 0:
                return False, "\n".join(logs)
        except Exception as exc:
            return False, f"$ {cmd}\nОШИБКА: {exc}"
    return True, "\n".join(logs)

# ========================= GIT =========================
def git_unstage_junk(project_path: str) -> None:
    for pattern in (".vibe", ".vibe/", ".aider", ".aider."):
        run_cmd([GIT_EXE, "rm", "-r", "--cached", "-f", "--ignore-unmatch", pattern],
                project_path, 30, env=base_env(), retries=2)

def git_commit_push(project_path: str, message: str) -> Tuple[str, str]:
    logs = []
    run_cmd([GIT_EXE, "add", "-A"], project_path, 60, env=base_env(), retries=3)
    git_unstage_junk(project_path)
    _, out = run_cmd([GIT_EXE, "status", "--porcelain"], project_path, 30, retries=3)
    if not out.strip():
        return "УСПЕХ_GIT", "нечего коммитить"
    msg = message[:72].replace("\n", " ")
    code, out = run_cmd([GIT_EXE, "commit", "-m", f"auto: {msg}"],
                        project_path, 60, env=base_env(), retries=3)
    logs.append(out[-800:])
    if code != 0 and "nothing to commit" not in out.lower() and "нечего коммитить" not in out.lower():
        return "КОД_ОК_GIT_СБОЙ", "\n".join(logs)
    for attempt in range(1, GIT_RETRIES + 1):
        code, out = run_cmd([GIT_EXE, "push"], project_path, 120, env=base_env(), retries=2)
        logs.append(f"push#{attempt}: {out[-400:]}")
        if code == 0:
            return "УСПЕХ_GIT", "\n".join(logs)
        time.sleep(2 * attempt)
    return "КОД_ОК_GIT_СБОЙ", "\n".join(logs)

# ========================= ОТЧЁТЫ / PROJECT STATE =========================
def project_dir(project_id: str) -> str:
    return os.path.join(PROJECTS_ROOT, project_id or DEFAULT_PROJECT)

def ensure_project_folders() -> None:
    """projects/ на Drive больше не обязателен — no-op (можно вернуть при необходимости)."""
    return


def append_project_history(project_id: str, status: str, executor: str,
                           task_text: str = "", detail: str = "") -> None:
    return


def update_project_state_activity(project_id: str, status: str, executor: str,
                                  task_text: str = "", detail: str = "") -> None:
    return


def log_project_outcome(project_id: str, status: str, executor: str,
                        task_name: str, detail: str = "") -> None:
    project_id = project_id or DEFAULT_PROJECT
    append_project_history(project_id, status, executor, task_name, detail)
    update_project_state_activity(project_id, status, executor, task_name)

def write_report(folder: str, prefix: str, status: str, project: str,
                 executor: str, task: str, detail: str) -> str:
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    name = f"{prefix}_{ts}_{project or 'na'}_{executor or 'na'}.md"
    try:
        log_project_outcome(project or DEFAULT_PROJECT, status, executor or "",
                           task or "", detail or "")
    except Exception:
        pass
    path = os.path.join(folder, name)
    write(path, f"# Отчёт {now()}\n\nСТАТУС: {status}\nПРОЕКТ: {project}\n"
                f"ИСПОЛНИТЕЛЬ: {executor}\nВРЕМЯ: {now()}\n\n"
                f"## Задача\n\n{task[:2000]}\n\n## Подробности\n\n```\n{detail[-4000:]}\n```\n")
    slog(f"[{now()}] отчёт → {name} [{status}]")
    return name

def archive_log_path() -> str:
    return os.path.join(LOGS, f"archive_{datetime.datetime.now().strftime('%Y%m')}.md")

def rotate_reports(folder: str, keep: int, label: str) -> int:
    if not os.path.isdir(folder):
        return 0
    names = [f for f in os.listdir(folder)
             if f.endswith((".md", ".txt")) and os.path.isfile(os.path.join(folder, f))]
    if len(names) <= keep:
        return 0
    names.sort(key=lambda f: os.path.getmtime(os.path.join(folder, f)), reverse=True)
    victims = names[keep:]
    lines = []
    for name in victims:
        p = os.path.join(folder, name)
        try:
            lines.append(
                f"{datetime.datetime.fromtimestamp(os.path.getmtime(p)).strftime('%Y-%m-%d %H:%M')} "
                f"| {label} | {name}"
            )
            os.remove(p)
        except OSError:
            pass
    if lines:
        os.makedirs(LOGS, exist_ok=True)
        with open(archive_log_path(), "a", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")
    return len(victims)

def cleanup_old_sessions() -> int:
    cutoff = time.time() - SESSION_KEEP_DAYS * 86400
    n = 0
    if not os.path.isdir(LOGS):
        return 0
    for name in os.listdir(LOGS):
        if not name.startswith("session_") or not name.endswith(".md"):
            continue
        p = os.path.join(LOGS, name)
        try:
            if os.path.getmtime(p) < cutoff:
                os.remove(p)
                n += 1
        except OSError:
            pass
    return n

def idle_bus_cleanup(force: bool = False) -> None:
    global LAST_CLEANUP
    if not force and time.time() - LAST_CLEANUP < CLEANUP_IDLE_SEC:
        return
    try:
        busy = (any(f.lower().endswith(SUPPORTED_EXT) for f in os.listdir(INCOMING))
                or any(f.lower().endswith(SUPPORTED_EXT) for f in os.listdir(PROCESSING)))
    except OSError:
        return
    if busy:
        return
    LAST_CLEANUP = time.time()
    rotate_reports(DONE, REPORT_KEEP, "done")
    rotate_reports(ERRORS, ERRORS_KEEP, "errors")
    cleanup_old_sessions()

# ========================= DEFERRED (RATE-LIMIT) =========================
def is_rate_limit_output(output: str) -> bool:
    low = (output or "").lower()
    return any(k in low for k in (
        "rate limit", "rate_limit", "429", "quota exceeded", "too many requests",
        "resource_exhausted", "limit exceeded", "daily limit", "usage limit",
        "try again later", "retry after", "ratelimit",
        "rate-limited", "you've hit", "you have hit", "hit your limit",
        "free limit", "request limit", "tokens per", "capacity exceeded",
        "temporarily rate", "throttl", "backoff",
    ))

def parse_rate_limit_seconds(output: str, default_sec: int = 3600) -> int:
    text = output or ""
    patterns = [
        (r"retry[- ]after[:\s]+(\d+)", 1),
        (r"(\d+)\s*(?:seconds?|сек)", 1),
        (r"(\d+)\s*(?:minutes?|мин)", 60),
        (r"(\d+)\s*(?:hours?|час)", 3600),
    ]
    for pattern, multiplier in patterns:
        match = re.search(pattern, text, re.I)
        if match:
            return max(60, min(int(match.group(1)) * multiplier, 86400))
    match = re.search(r"(?:until|до)\s+(\d{1,2}):(\d{2})", text, re.I)
    if match:
        now_dt = datetime.datetime.now()
        target = now_dt.replace(hour=int(match.group(1)), minute=int(match.group(2)),
                                second=0, microsecond=0)
        if target <= now_dt:
            target += datetime.timedelta(days=1)
        return max(60, min(int((target - now_dt).total_seconds()), 86400))
    return default_sec

def load_rate_limit_until() -> float:
    global CLOUD_RATE_LIMIT_UNTIL
    try:
        CLOUD_RATE_LIMIT_UNTIL = float(
            json.loads(read(RATE_LIMIT_STATE) or "{}").get("until", 0) or 0
        )
    except Exception:
        CLOUD_RATE_LIMIT_UNTIL = 0.0
    return CLOUD_RATE_LIMIT_UNTIL

def save_rate_limit_until(until: float) -> None:
    global CLOUD_RATE_LIMIT_UNTIL
    CLOUD_RATE_LIMIT_UNTIL = until
    write(RATE_LIMIT_STATE, json.dumps({"until": until, "saved": now()}, ensure_ascii=False, indent=2))

def defer_task_file(src: str, filename: str, reason: str, wait_sec: int) -> None:
    os.makedirs(DEFERRED, exist_ok=True)
    dest = os.path.join(DEFERRED, filename)
    if os.path.exists(dest):
        base, ext = os.path.splitext(filename)
        dest = os.path.join(DEFERRED, f"{base}_d{ext}")
    if os.path.exists(src):
        shutil.move(src, dest)
    until = time.time() + wait_sec
    write(dest + ".wait", json.dumps({"until": until, "reason": reason[:500]}, ensure_ascii=False))
    save_rate_limit_until(until)

def resume_deferred() -> int:
    os.makedirs(DEFERRED, exist_ok=True)
    now_ts = time.time()
    n = 0
    global_until = load_rate_limit_until()
    if global_until and now_ts < global_until:
        return 0
    for name in os.listdir(DEFERRED):
        if name.endswith(".wait") or not name.lower().endswith(SUPPORTED_EXT):
            continue
        p = os.path.join(DEFERRED, name)
        wp = p + ".wait"
        ready = True
        if os.path.exists(wp):
            try:
                ready = float(json.loads(read(wp) or "{}").get("until", 0)) <= now_ts
            except Exception:
                ready = True
        if not ready:
            continue
        dest = os.path.join(INCOMING, name)
        if os.path.exists(dest):
            base, ext = os.path.splitext(name)
            dest = os.path.join(INCOMING, f"{base}_resumed{ext}")
        try:
            shutil.move(p, dest)
            if os.path.exists(wp):
                os.remove(wp)
            n += 1
        except OSError:
            pass
    if n and global_until and now_ts >= global_until:
        save_rate_limit_until(0)
    return n

# ========================= GEMINI DOCS =========================
def _drive_service():
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
    scopes = ["https://www.googleapis.com/auth/drive"]
    creds = None
    if os.path.exists(GEMINI_TOKEN):
        creds = Credentials.from_authorized_user_file(GEMINI_TOKEN, scopes)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(GEMINI_CREDENTIALS):
                raise RuntimeError(f"нет credentials: {GEMINI_CREDENTIALS}")
            creds = InstalledAppFlow.from_client_secrets_file(GEMINI_CREDENTIALS, scopes).run_local_server(port=0)
        os.makedirs(os.path.dirname(GEMINI_TOKEN), exist_ok=True)
        write(GEMINI_TOKEN, creds.to_json())
    return build("drive", "v3", credentials=creds)

def _ensure_folder(service, name: str, parent_id=None):
    parent_clause = f"'{parent_id}' in parents" if parent_id else "'root' in parents"
    query = f"name = '{name}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false and {parent_clause}"
    result = service.files().list(q=query, spaces="drive", fields="files(id)", pageSize=3).execute()
    files = result.get("files") or []
    if files:
        return files[0]["id"]
    body = {"name": name, "mimeType": "application/vnd.google-apps.folder"}
    if parent_id:
        body["parents"] = [parent_id]
    return service.files().create(body=body, fields="id").execute()["id"]

def _agentbus_folder_id(service):
    query = "name = 'AgentBus' and mimeType = 'application/vnd.google-apps.folder' and trashed = false and 'root' in parents"
    try:
        files = service.files().list(q=query, spaces="drive", fields="files(id)", pageSize=3).execute().get("files") or []
        return files[0]["id"] if files else None
    except Exception:
        return None

def _flag_path(doc_id: str) -> str:
    return os.path.join(GEMINI_ARCHIVE, f"processed_{doc_id}.flag")

def poll_gemini_docs() -> int:
    global _last_gemini_poll
    if not GEMINI_DOCS_ENABLED or time.time() - _last_gemini_poll < GEMINI_POLL_SEC:
        return 0
    _last_gemini_poll = time.time()
    try:
        service = _drive_service()
    except Exception as exc:
        slog(f"[{now()}] gemini API: {exc}")
        return 0
    query = "mimeType = 'application/vnd.google-apps.document' and trashed = false"
    if GEMINI_SOURCE_FOLDER_ID:
        query += f" and '{GEMINI_SOURCE_FOLDER_ID}' in parents"
    try:
        docs = service.files().list(q=query, spaces="drive", fields="files(id,name,parents)",
                                    orderBy="modifiedTime desc", pageSize=10).execute().get("files") or []
    except Exception as exc:
        slog(f"[{now()}] gemini list: {exc}")
        return 0
    n = 0
    processed_id = None
    os.makedirs(GEMINI_ARCHIVE, exist_ok=True)
    os.makedirs(INCOMING, exist_ok=True)
    for doc in docs:
        doc_id = doc["id"]
        name = doc.get("name") or "без_названия"
        if os.path.exists(_flag_path(doc_id)):
            continue
        parents = doc.get("parents") or []
        try:
            if processed_id is None:
                processed_id = _ensure_folder(service, GEMINI_PROCESSED_FOLDER, _agentbus_folder_id(service))
            if processed_id in parents:
                write(_flag_path(doc_id), now())
                continue
        except Exception:
            pass
        try:
            data = service.files().export(fileId=doc_id, mimeType="text/plain").execute()
            text = data.decode("utf-8", errors="replace") if isinstance(data, bytes) else str(data)
        except Exception as exc:
            slog(f"[{now()}] gemini export {name}: {exc}")
            continue
        if len(text.strip()) < 10:
            write(_flag_path(doc_id), now())
            continue
        if looks_like_roadmap_noise(text) and "FILES:" not in text.upper():
            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            safe = re.sub(r"[^\w\-]+", "_", name)[:40]
            write(os.path.join(GEMINI_ARCHIVE, f"skipped_{ts}_{safe}.md"), text)
            write(_flag_path(doc_id), now())
            continue
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        safe = re.sub(r"[^\w\-]+", "_", name)[:40]
        header = f"# Задача из Google Doc\nAUTHOR: gemini\nCREATED: {now()}\nSOURCE_DOC_ID: {doc_id}\nSOURCE_TITLE: {name}\n\n"
        if "PROJECT:" in text.upper():
            body = header + text
        else:
            body = header + f"PROJECT: {DEFAULT_PROJECT}\nEXECUTOR: aider\nallow_no_files: false\n\nMESSAGE: |\n" + "\n".join("  " + x for x in text.splitlines()) + "\n"
        write(os.path.join(GEMINI_ARCHIVE, f"gemini_{ts}_{safe}.md"), body)
        write(os.path.join(INCOMING, f"tasks_{ts}_gemini_{safe}.md"), body)
        write(_flag_path(doc_id), now())
        try:
            if processed_id is None:
                processed_id = _ensure_folder(service, GEMINI_PROCESSED_FOLDER, _agentbus_folder_id(service))
            service.files().update(fileId=doc_id, addParents=processed_id,
                                   removeParents=",".join(parents) if parents else "root", fields="id").execute()
        except Exception as exc:
            slog(f"[{now()}] gemini move: {exc}")
        n += 1
    return n

# ========================= ОБРАБОТКА ЗАДАЧИ =========================
def resolve_project(pid: str):
    pid = (pid or DEFAULT_PROJECT).strip()
    if pid not in PROJECTS:
        return None, None, f"НЕИЗВЕСТНЫЙ_ПРОЕКТ: {pid}"
    info = PROJECTS[pid]
    if not os.path.isdir(info["path"]):
        return pid, info, f"НЕТ_ПАПКИ_ПРОЕКТА: {info['path']}"
    return pid, info, ""

def make_prompt(project_id: str, project_path: str, task: str, files: List[str]) -> str:
    fl = ", ".join(files) if files else "(см. текст задачи)"
    return (f"Проект: {project_id}\nКорень git: {project_path}\n"
            f"Работай ТОЛЬКО внутри этой папки. НЕ делай git commit/push.\n"
            f"НЕ вставляй shell/git команды внутрь .py файлов.\n"
            f"Целевые файлы: {fl}\n"
            f"Не спрашивай, какие файлы править — правь только целевые.\n\nЗадача:\n{task}\n")

def handle_coder_failure(project_id, used, task_text, output, task_path, filename,
                         is_supabase=False, supabase_id=None) -> bool:
    """True = ошибка обработана (не писать fail). Rate-limit → пауза + отложить."""
    if used == "opencode" and (is_rate_limit_output(output) or "лимит активен" in (output or "").lower()):
        wait_sec = parse_rate_limit_seconds(output, default_sec=3600)
        save_rate_limit_until(time.time() + wait_sec)
        slog(f"[{now()}] задача отложена на {wait_sec}с из-за лимита OpenCode")
        if is_supabase and supabase_id:
            # Вернуть в очередь PENDING — не fail. Кириллица только в JSON body (UTF-8).
            err_msg = f"rate_limit: retry_in_{wait_sec}s"
            supabase_request(
                "PATCH", "/rest/v1/agentbus_tasks",
                payload={
                    "status": "PENDING",
                    "worker_id": None,
                    "claimed_at": None,
                    "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    "error": err_msg,
                },
                query={
                    "id": f"eq.{supabase_id}",
                    "status": "eq.CLAIMED",
                    "worker_id": f"eq.{WORKER_ID}",
                },
            )
            slog(f"[{now()}] Supabase задача {supabase_id} → PENDING (лимит)")
        elif task_path and filename:
            defer_task_file(task_path, filename, f"rate_limit:{output[:200]}", wait_sec)
        else:
            # нет локального файла — глобальный таймер уже сохранён
            pass
        try:
            log_project_outcome(project_id, "ОТЛОЖЕНО_ЛИМИТ", used, task_text, f"wait {wait_sec}s")
        except Exception:
            pass
        return True
    return False

def process_task(meta: dict, task_text: str, filename: str,
                local_path: Optional[str] = None, supabase_id: Optional[str] = None):
    global FAIL_STREAK, TASKS_DONE_CYCLE, CURRENT_SUPABASE_TASK_ID
    is_sb = bool(supabase_id)
    project_id, info, err = resolve_project(meta.get("project") or DEFAULT_PROJECT)
    executor = (meta.get("executor") or "aider").lower()
    if executor in ("cloud", "opencode-cloud"):
        executor = "opencode"
    if err:
        if is_sb:
            fail_supabase_task(supabase_id, err)
        write_report(ERRORS, "fail", "НЕИЗВЕСТНЫЙ_ПРОЕКТ", meta.get("project", ""), executor, filename, err)
        FAIL_STREAK += 1
        return
    files = list(meta.get("files") or [])
    if not task_text or looks_like_roadmap_noise(task_text):
        detail = "пустая задача или дорожная карта"
        if is_sb:
            fail_supabase_task(supabase_id, detail)
        write_report(ERRORS, "fail", "ПЛОХАЯ_СПЕКА", project_id, executor, filename, detail)
        return
    if REQUIRE_FILES and not meta.get("allow_no_files") and not files:
        files = list(dict.fromkeys(re.findall(r"[\w./\\-]+\.py\b", task_text)))[:8]
    if REQUIRE_FILES and not meta.get("allow_no_files") and not files:
        detail = "Нет FILES. Нужно явно: FILES: path/to/file.py"
        if is_sb:
            fail_supabase_task(supabase_id, detail)
        write_report(ERRORS, "fail", "ПЛОХАЯ_СПЕКА", project_id, executor, filename, detail)
        return
    bad = [f for f in files if not path_allowed(info["path"], f)]
    if bad and not meta.get("allow_no_files"):
        detail = f"недопустимые пути: {bad}"
        if is_sb:
            fail_supabase_task(supabase_id, detail)
        write_report(ERRORS, "fail", "ПЛОХАЯ_СПЕКА", project_id, executor, filename, detail)
        return
    if executor == "aider" and is_complex_task(task_text, files):
        slog(f"[{now()}] сложная/мультифайл → opencode")
        executor = "opencode"
    project_path = info["path"]
    prompt = make_prompt(project_id, project_path, task_text, files)
    before = snapshot_mtimes(project_path, files)
    used = executor
    code = 1
    output = ""
    if executor == "git-only":
        status, detail = git_commit_push(project_path, task_text[:60])
        if is_sb:
            if status == "УСПЕХ_GIT":
                finish_supabase_task(supabase_id, detail)
            else:
                fail_supabase_task(supabase_id, detail)
        write_report(DONE if status == "УСПЕХ_GIT" else ERRORS,
                    "report" if status == "УСПЕХ_GIT" else "need_push",
                    status, project_id, "git-only", task_text, detail)
        return
    if executor == "aider":
        for attempt in range(1, MAX_TRIES + 1):
            supabase_heartbeat()
            code, output = run_aider(prompt, files, project_path)
            if is_code_ok(code, output):
                break
            if is_clarify(output):
                until = load_rate_limit_until()
                if (AIDER_FALLBACK_TO_OPENCODE and ALLOW_CLOUD_FALLBACK and cloud_budget_left() > 0
                        and not (until and time.time() < until)):
                    used = "opencode"
                    code, output = run_opencode(prompt, project_path, meta.get("model") or "")
                break
            if is_infra_fail(output):
                time.sleep(5)
                continue
            time.sleep(2)
        else:
            until = load_rate_limit_until()
            if (AIDER_FALLBACK_TO_OPENCODE and ALLOW_CLOUD_FALLBACK and cloud_budget_left() > 0
                    and not (until and time.time() < until)):
                used = "opencode"
                code, output = run_opencode(prompt, project_path, meta.get("model") or "")
    else:
        # облако: если глобальный лимит — сразу отложить, без запуска
        until = load_rate_limit_until()
        if until and time.time() < until:
            left = int(until - time.time())
            output = f"облачный лимит активен ещё {left}с"
            used = "opencode"
            code = 429
        else:
            code, output = run_opencode(prompt, project_path, meta.get("model") or "")
    if not is_code_ok(code, output):
        if handle_coder_failure(project_id, used, task_text, output, local_path, filename, is_sb, supabase_id):
            return
        detail = output[-3000:]
        if is_sb:
            fail_supabase_task(supabase_id, detail)
        write_report(ERRORS, "fail", "СБОЙ_КОДА", project_id, used, task_text, detail)
        FAIL_STREAK += 1
        return
    supabase_heartbeat()
    ok, vmsg = verify_task(project_path, meta, files)
    if not ok:
        if is_sb:
            fail_supabase_task(supabase_id, vmsg)
        write_report(ERRORS, "fail", "ПРОВЕРКА_НЕ_ПРОШЛА", project_id, used, task_text, vmsg + "\n" + output[-1500:])
        FAIL_STREAK += 1
        return
    if meta.get("run"):
        rok, rlog = run_task_commands(project_path, meta["run"])
        if not rok:
            if is_sb:
                fail_supabase_task(supabase_id, rlog)
            write_report(ERRORS, "fail", "СБОЙ_RUN", project_id, used, task_text, rlog)
            FAIL_STREAK += 1
            return
        output += "\n--- RUN ---\n" + rlog
    if not GIT_ENABLED:
        if is_sb:
            finish_supabase_task(supabase_id, output[-5000:])
        write_report(DONE, "report", "КОД_ОК", project_id, used, task_text, output[-2000:])
        FAIL_STREAK = 0
        TASKS_DONE_CYCLE += 1
        return
    status, glog = git_commit_push(project_path, task_text[:60])
    detail = output[-1500:] + "\n--- git ---\n" + glog
    if status == "УСПЕХ_GIT":
        if is_sb:
            finish_supabase_task(supabase_id, detail)
        write_report(DONE, "report", "УСПЕХ_GIT", project_id, used, task_text, detail)
        FAIL_STREAK = 0
        TASKS_DONE_CYCLE += 1
    else:
        if is_sb:
            fail_supabase_task(supabase_id, detail)
        write_report(ERRORS, "need_push", status, project_id, used, task_text, detail)
        FAIL_STREAK += 1

def process_local_file(path: str, filename: str) -> None:
    raw = read(path)
    meta = parse_meta(raw)
    tasks = extract_tasks(meta, raw)
    process_task(meta, tasks[0] if tasks else "", filename, local_path=path)

# ========================= STARTUP / SHUTDOWN =========================
def boot_checks() -> List[str]:
    problems = []
    if not os.path.isfile(AIDER):
        problems.append(f"AIDER не найден: {AIDER}")
    if not os.path.isfile(OPENCODE):
        problems.append(f"OPENCODE не найден: {OPENCODE}")
    git = GIT_EXE if os.path.exists(GIT_EXE) else "git"
    code, out = run_cmd([git, "--version"], DRIVE, 15, env=base_env(), retries=3)
    if code != 0:
        problems.append(f"git недоступен: {out[:200]}")
        return problems
        seen_paths = set()
    for pid, info in PROJECTS.items():
        path = info.get("path") or ""
        if path in seen_paths:
            continue
        seen_paths.add(path)
        if not path or not os.path.isdir(path):
            problems.append(
                f"нет папки проекта {pid}: {path or '(пусто)'} — "
                f"пропиши PROJECT_PREDICTION_ANALYZER=... в .env или клонируй репу"
            )

            continue
        code, out = run_cmd([git, "rev-parse", "--is-inside-work-tree"],
                           info["path"], 15, env=base_env(), retries=3)
        if code != 0 or "true" not in out.lower():
            problems.append(f"не git-репозиторий: {info['path']}")
    return problems

def recover_stale(force_all: bool = False) -> int:
    n = 0
    now_ts = time.time()
    try:
        names = os.listdir(PROCESSING)
    except OSError:
        return 0
    for name in names:
        if not name.lower().endswith(SUPPORTED_EXT):
            continue
        p = os.path.join(PROCESSING, name)
        try:
            age = now_ts - os.path.getmtime(p)
            if force_all or age > STALE_TIME:
                dest = os.path.join(INCOMING, name)
                if os.path.exists(dest):
                    base, ext = os.path.splitext(name)
                    dest = os.path.join(INCOMING, f"{base}_retry{ext}")
                shutil.move(p, dest)
                n += 1
        except OSError:
            pass
    return n

def list_incoming() -> List[str]:
    try:
        files = [f for f in os.listdir(INCOMING) if f.lower().endswith(SUPPORTED_EXT)]
        files.sort(key=lambda f: os.path.getmtime(os.path.join(INCOMING, f)))
        return files
    except OSError:
        return []

def wait_stable(path: str, timeout: int = 30) -> bool:
    prev = -1
    start = time.time()
    while time.time() - start < timeout:
        try:
            cur = os.path.getsize(path)
        except OSError:
            return False
        if cur == prev:
            return True
        prev = cur
        time.sleep(2)
    return False

def handle_signal(signum, frame):
    global SHUTTING_DOWN
    SHUTTING_DOWN = True
    slog(f"[{now()}] остановка signal={signum}")
    if CURRENT_SUPABASE_TASK_ID:
        requeue_current_supabase_task(CURRENT_SUPABASE_TASK_ID)

def main_loop() -> None:
    global LAST_BEAT, FAIL_STREAK, TASKS_DONE_CYCLE, CURRENT_SUPABASE_TASK_ID
    apply_network_env()
    try:
        ensure_channel_dirs()
    except Exception:
        pass
    for directory in (INCOMING, PROCESSING, DONE, ERRORS, DEFERRED, LOGS, GEMINI_ARCHIVE):
        os.makedirs(directory, exist_ok=True)
    ensure_project_folders()
    write(SESSION_LOG, f"# AgentBus Dispatcher {VERSION}\n\nСтарт: {now()}\n"
                       f".env: {ENV_FILE_LOADED or 'не найден'}\n"
                       f"Supabase: {'вкл' if supabase_enabled() else 'выкл/не настроен'}\n"
                       f"Worker: {WORKER_ID}\n\n---\n")
    append_log(DISPATCHER_LOG, f"\n===== SESSION {SESSION_ID} v{VERSION} {now()} =====\n")
    slog(f"[{now()}] === AgentBus Dispatcher v{VERSION} ===")
    slog(f"[{now()}] Шина: {INCOMING}")
    slog(f"[{now()}] Логи: {LOGS}")
    slog(f"[{now()}] Лимит OpenCode → deferred + rate_limit_until.json")
    if ENV_FILE_LOADED:
        slog(f"[{now()}] .env загружен: {ENV_FILE_LOADED}")
    else:
        slog(f"[{now()}] .env не найден; используются системные переменные")
    if supabase_enabled():
        slog(f"[{now()}] Supabase: {SUPABASE_URL} | worker={WORKER_ID}")
    else:
        slog(f"[{now()}] Supabase отключён: проверьте SUPABASE_URL/SUPABASE_SERVICE_ROLE_KEY")
    problems = boot_checks()
    for problem in problems:
        slog(f"[{now()}] BOOT: {problem}")
    recover_stale(True)
    load_rate_limit_until()
    resume_deferred()
    idle_bus_cleanup(True)
    signal.signal(signal.SIGINT, handle_signal)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, handle_signal)
    while not SHUTTING_DOWN:
        try:
            if FAIL_STREAK >= CIRCUIT_BREAKER_LIMIT:
                slog(f"[{now()}] circuit breaker: сон {CIRCUIT_SLEEP_SEC}s")
                time.sleep(CIRCUIT_SLEEP_SEC)
                FAIL_STREAK = 0
            recover_stale(False)
            resume_deferred()
            requeue_stale_supabase_tasks()
            if GEMINI_DOCS_ENABLED:
                try:
                    poll_gemini_docs()
                except Exception as exc:
                    slog(f"[{now()}] gemini poll: {exc}")
            supabase_heartbeat()
            files = list_incoming()
            if files:
                if TASKS_DONE_CYCLE >= MAX_TASKS_PER_CYCLE:
                    TASKS_DONE_CYCLE = 0
                    time.sleep(30)
                    continue
                filename = files[0]
                incoming_path = os.path.join(INCOMING, filename)
                processing_path = os.path.join(PROCESSING, filename)
                if not wait_stable(incoming_path):
                    time.sleep(3)
                    continue
                shutil.move(incoming_path, processing_path)
                slog(f"[{now()}] local → processing: {filename}")
                try:
                    process_local_file(processing_path, filename)
                except Exception as exc:
                    slog(f"[{now()}] local task exception: {exc}")
                finally:
                    if os.path.exists(processing_path):
                        try:
                            os.remove(processing_path)
                        except OSError:
                            pass
                continue
            task = claim_supabase_task()
            if task:
                CURRENT_SUPABASE_TASK_ID = task["id"]
                slog(f"[{now()}] Supabase CLAIMED id={task['id']} project={task['project']} executor={task['executor']}")
                # зеркало задачи в лог канала (удобно смотреть без БД)
                try:
                    snap = (
                        f"# Supabase task {task['id']}\n"
                        f"PROJECT: {task.get('project')}\n"
                        f"EXECUTOR: {task.get('executor')}\n"
                        f"AUTHOR: {task.get('author') or 'gpt'}\n"
                        f"CLAIMED: {now()}\n\n"
                        f"{task.get('message') or ''}\n"
                    )
                    write(os.path.join(LOGS, f"task_{task['id'][:8]}_{SESSION_ID}.md"), snap)
                except Exception:
                    pass
                meta = {k: task.get(k) for k in ("project", "executor", "model", "files", "verify", "run", "allow_no_files", "author")}
                try:
                    process_task(meta, task["message"], f"supabase_{task['id']}", supabase_id=task["id"])
                except Exception as exc:
                    fail_supabase_task(task["id"], str(exc))
                    slog(f"[{now()}] supabase task exception: {exc}")
                finally:
                    CURRENT_SUPABASE_TASK_ID = None
                continue
            if time.time() - LAST_BEAT > 300:
                slog(f"[{now()}] жив, жду задачи")
                LAST_BEAT = time.time()
                TASKS_DONE_CYCLE = 0
            idle_bus_cleanup(False)
            time.sleep(2)
        except KeyboardInterrupt:
            break
        except Exception as exc:
            slog(f"[{now()}] ошибка диспетчера: {exc}")
            time.sleep(10)
    if CURRENT_SUPABASE_TASK_ID:
        requeue_current_supabase_task(CURRENT_SUPABASE_TASK_ID)
    slog(f"[{now()}] диспетчер остановлен")

if __name__ == "__main__":
    main_loop()
