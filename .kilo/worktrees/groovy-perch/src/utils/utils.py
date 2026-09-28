# -*- coding: utf-8 -*-
"""Общие утилиты: env, токенизация, пути."""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

_TOKEN_RE = re.compile(r"[a-zA-Zа-яА-ЯёЁ0-9_]{2,}")


def env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def env_flag(name: str) -> bool:
    return (os.getenv(name) or "").strip().lower() in ("1", "true", "yes", "on")


def env_path(name: str, default: str) -> Path:
    raw = (os.getenv(name) or "").strip()
    return Path(raw) if raw else Path(default)


def tokenize_text(text: str) -> set[str]:
    return {t.lower() for t in _TOKEN_RE.findall(text or "")}


def tokenize_text_list(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text or "")]


def normalize_path(path: str) -> str:
    return str(path).replace("\\", "/").lstrip("./")


def extract_files(task: dict[str, Any]) -> list[str]:
    files = task.get("files") or task.get("paths") or []
    if isinstance(files, str):
        files = [files]
    return [normalize_path(f) for f in files if f]
