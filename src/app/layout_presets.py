# -*- coding: utf-8 -*-
"""Compat alias for layout_prefs."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from app.layout_prefs import (
    apply_layout_preset,
    get_layout,
    list_layout_presets,
    save_layout,
)


def apply_preset(name: str, *, config_root: str | Path | None = None) -> dict[str, Any]:
    root = Path(config_root) if config_root else None
    return apply_layout_preset(name, root=root)


def load_layout(config_root: str | Path | None = None) -> dict[str, Any]:
    root = Path(config_root) if config_root else None
    return get_layout(root)


PRESETS = {
    "agent": {"mode": "agent"},
    "code": {"mode": "code"},
    "focus": {"mode": "code", "show_right": False},
    "full": {"mode": "full"},
}
