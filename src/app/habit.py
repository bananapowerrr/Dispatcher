# -*- coding: utf-8 -*-
"""Soft habit suggestions — never change profile silently."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


def _path(root: Path | None = None) -> Path:
    if root is None:
        try:
            from core.config import BASE_DIR
            root = Path(BASE_DIR)
        except Exception:
            root = Path.cwd()
    return Path(root) / ".agentbus" / "habit.json"


def load_habit(root: Path | None = None) -> dict[str, Any]:
    p = _path(root)
    if not p.is_file():
        return {"continue_accepts": 0, "prompted_profile": False, "last_prompt_at": 0}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {"continue_accepts": 0, "prompted_profile": False, "last_prompt_at": 0}


def save_habit(data: dict[str, Any], root: Path | None = None) -> None:
    p = _path(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def record_continue_accept(root: Path | None = None, *, threshold: int = 5) -> dict[str, Any]:
    """Count Continues that accept agent defaults. Return optional prompt.

    Never mutates AgentBehavior — only suggests once.
    """
    h = load_habit(root)
    h["continue_accepts"] = int(h.get("continue_accepts") or 0) + 1
    out: dict[str, Any] = {
        "count": h["continue_accepts"],
        "suggest_profile": False,
        "message": "",
    }
    if not h.get("prompted_profile") and h["continue_accepts"] >= threshold:
        out["suggest_profile"] = True
        out["message"] = (
            "Похоже, вы обычно принимаете рекомендации без правок. "
            "Сделать текущий профиль агента стандартным? "
            "Откройте Agent · … или оставьте как есть."
        )
        h["prompted_profile"] = True
        h["last_prompt_at"] = time.time()
    save_habit(h, root)
    return out


def reset_habit(root: Path | None = None) -> None:
    save_habit(
        {"continue_accepts": 0, "prompted_profile": False, "last_prompt_at": 0},
        root,
    )
