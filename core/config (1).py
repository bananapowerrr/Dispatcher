# -*- coding: utf-8 -*-
"""Константы, пути, проекты AgentBus."""
from __future__ import annotations

import datetime
import os
import re
import sys
import time
from typing import Dict, List, Optional, Tuple

VERSION = "1.0"

DRIVE = os.environ.get("AGENTBUS_DRIVE", r"G:\Мой диск\AgentBus").strip() or r"G:\Мой диск\AgentBus"
OPENCODE = os.environ.get("OPENCODE_EXE", r"D:\Progs\opencode.exe")
AIDER = os.environ.get(
    "AIDER_EXE",
    r"C:\Users\user\AppData\Local\Programs\Python\Python312\Scripts\aider.exe",
)
GIT_EXE = os.environ.get("GIT_EXE", r"C:\Program Files\Git\cmd\git.exe")
PYTHON_EXE = sys.executable  # тот же интерпретатор, что запустил диспетчер (лучше 3.12)

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
CLOUD_USAGE_FILE = os.path.join(DRIVE, "cloud_usage.json")

# --- Supabase (логика RPC не меняется) ---
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

import socket
WORKER_ID = (
    os.getenv("AGENTBUS_WORKER_ID", "").strip()
    or f"{socket.gethostname()}-{os.getpid()}-{datetime.datetime.now().strftime('%Y%m%d-%H%M%S')}"
)

# --- Gemini (запасной) ---
GEMINI_DOCS_ENABLED = os.getenv("GEMINI_DOCS_ENABLED", "0").strip().lower() in {"1", "true", "yes", "on"}
GEMINI_SOURCE_FOLDER_ID = None
GEMINI_PROCESSED_FOLDER = os.path.join(CHANNELS_ROOT, "gemini", "done")
GEMINI_CREDENTIALS = os.path.join(DRIVE, "credentials", "credentials.json")
GEMINI_TOKEN = os.path.join(DRIVE, "credentials", "token.json")
GEMINI_POLL_SEC = 60

# --- Проекты ---
PROJECTS = {
    "prediction-analyzer": {
        "path": os.getenv("PROJECT_PREDICTION_ANALYZER", r"D:\Workspace\Prediction-Analyzer"),
        "repo": "bananapowerrr/Prediction-Analyzer",
    },
    "desktop-tutorial": {
        "path": os.getenv("PROJECT_PREDICTION_ANALYZER", r"D:\Workspace\Prediction-Analyzer"),
        "repo": "bananapowerrr/Prediction-Analyzer",
    },
    "dispatcher": {
        "path": os.getenv("PROJECT_DISPATCHER", r"D:\Workspace\Dispatcher"),
        "repo": "bananapowerrr/Dispatcher",
    },
}
DEFAULT_PROJECT = "prediction-analyzer"

PROXY_URL = os.getenv("PROXY_URL", "").strip()

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
CIRCUIT_BREAKER_LIMIT = 8
CIRCUIT_SLEEP_SEC = 300
MAX_TASKS_PER_CYCLE = 15
WRITE_SUCCESS_REPORTS = True
REPORT_KEEP = 10
ERRORS_KEEP = 30
ERRORS_ROTATE_SEC = 12 * 3600
CLEANUP_IDLE_SEC = 90
SESSION_KEEP_DAYS = 3

# pip install -r requirements.txt перед pytest (если задача просит)
AUTO_PIP_INSTALL = os.getenv("AUTO_PIP_INSTALL", "1").strip().lower() not in {"0", "false", "no"}

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
    r"дорожн\w*\s+карт", r"мастер[- ]?список", r"фаза\s*[0-9]", r"phase\s*[0-9]",
    r"сводн\w*\s+таблиц", r"техническ\w*\s+задани",
]
BAD_SIGNS = [
    "traceback (most recent call last)", "permission denied", "отказано в доступе",
    "malformed edit", "не удалось",
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
