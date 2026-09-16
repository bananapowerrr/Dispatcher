# -*- coding: utf-8 -*-
"""Minimal i18n: load config/strings_{lang}.yaml."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

from core.config import BASE_DIR

_cache: dict[str, dict[str, Any]] = {}
_current_lang: str | None = None


def _lang() -> str:
    global _current_lang
    if _current_lang:
        return _current_lang
    env = (os.getenv("AGENTBUS_LANG") or "").strip().lower()
    if env in ("ru", "en"):
        return env
    try:
        from safety.language_guard import get_agent_language
        return get_agent_language()
    except Exception:
        return "ru"


def set_language(lang: str) -> str:
    """Process-local language override (clears string cache)."""
    global _current_lang
    lang = (lang or "ru").strip().lower()
    if lang not in ("ru", "en"):
        lang = "ru"
    _current_lang = lang
    os.environ["AGENTBUS_LANG"] = lang
    clear_cache()
    return lang


def clear_cache() -> None:
    _cache.clear()


def load_strings(lang: str | None = None) -> dict[str, Any]:
    lang = (lang or _lang()).lower()
    if lang in _cache:
        return _cache[lang]
    path = BASE_DIR / "config" / f"strings_{lang}.yaml"
    data: dict[str, Any] = {}
    if path.is_file():
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            if isinstance(raw, dict):
                data = raw
        except Exception:
            data = {}
    _cache[lang] = data
    return data


def t(key: str, default: str | None = None, **fmt: Any) -> str:
    """Translate key; fallback to default or key."""
    data = load_strings()
    val = data.get(key)
    if val is None:
        # try other language as soft fallback
        other = "en" if _lang() == "ru" else "ru"
        val = load_strings(other).get(key)
    if val is None:
        text = default if default is not None else key
    else:
        text = str(val)
    if fmt:
        try:
            return text.format(**fmt)
        except Exception:
            return text
    return text
