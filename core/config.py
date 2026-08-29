# -*- coding: utf-8 -*-
"""Constants and project paths (optional helpers for small modules)."""
from __future__ import annotations

import datetime
import os
import socket
import sys

VERSION = "1.0"
DRIVE = os.environ.get("AGENTBUS_DRIVE", r"G:\Мой диск\AgentBus").strip() or r"G:\Мой диск\AgentBus"
OPENCODE = os.environ.get("OPENCODE_EXE", r"D:\Progs\opencode.exe")
AIDER = os.environ.get(
    "AIDER_EXE",
    r"C:\Users\user\AppData\Local\Programs\Python\Python312\Scripts\aider.exe",
)
GIT_EXE = os.environ.get("GIT_EXE", r"C:\Program Files\Git\cmd\git.exe")
PYTHON_EXE = sys.executable

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

def _first_existing(*candidates: str) -> str:
    for c in candidates:
        c = (c or "").strip().strip('"').strip("'")
        if c and os.path.isdir(c):
            return c
    return (candidates[0] if candidates else "") or ""

_PA_PATH = _first_existing(
    os.getenv("PROJECT_PREDICTION_ANALYZER", r"D:\Workspace\Prediction-Analyzer").strip(),
    r"D:\Workspace\Prediction-Analyzer",
)
_DISP_PATH = _first_existing(
    os.getenv("PROJECT_DISPATCHER", r"G:\Мой диск\AgentBus").strip(),
    r"G:\Мой диск\AgentBus",
)

PROJECTS = {
    "prediction-analyzer": {"path": _PA_PATH, "repo": "bananapowerrr/Prediction-Analyzer"},
    "desktop-tutorial": {"path": _PA_PATH, "repo": "bananapowerrr/Prediction-Analyzer"},
    "dispatcher": {"path": _DISP_PATH, "repo": "bananapowerrr/Dispatcher"},
}
DEFAULT_PROJECT = "prediction-analyzer"
