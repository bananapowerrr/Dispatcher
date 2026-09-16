# -*- coding: utf-8 -*-
"""Optional custom skills loader (feature-flagged)."""
from __future__ import annotations

import importlib.util
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger("agentbus.skills.custom")


def load_custom_skills(registry: Any, custom_dir: str | Path | None = None) -> list[str]:
    """Load skill_* callables from custom dir into registry.

    Disabled unless AGENTBUS_LOAD_CUSTOM_SKILLS=1 or feature load_custom_skills.
    Returns list of registered skill names.
    """
    enabled = os.getenv("AGENTBUS_LOAD_CUSTOM_SKILLS", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    if not enabled:
        try:
            from core.feature_flags import is_enabled
            enabled = bool(is_enabled("load_custom_skills", default=False))
        except Exception:
            enabled = False
    if not enabled:
        return []

    if custom_dir is None:
        # Prefer project BASE_DIR/src/skills/custom (tests patch BASE_DIR)
        try:
            from core.config import BASE_DIR
            custom_dir = Path(BASE_DIR) / "src" / "skills" / "custom"
        except Exception:
            custom_dir = Path(__file__).resolve().parent / "custom"
    root = Path(custom_dir)
    if not root.is_dir():
        return []

    loaded: list[str] = []
    for path in sorted(root.glob("*.py")):
        if path.name.startswith("_"):
            continue
        try:
            spec = importlib.util.spec_from_file_location(
                f"agentbus_custom_{path.stem}", path
            )
            if spec is None or spec.loader is None:
                continue
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            for attr in dir(mod):
                if not attr.startswith("skill_"):
                    continue
                fn = getattr(mod, attr)
                if not callable(fn):
                    continue
                name = attr[len("skill_") :]
                # registry may expose register(name, fn) or skills dict
                if hasattr(registry, "register"):
                    registry.register(name, fn, description=f"custom:{name}")
                elif hasattr(registry, "SKILLS") and isinstance(registry.SKILLS, dict):
                    registry.SKILLS[name] = fn
                elif hasattr(registry, "skills") and isinstance(registry.skills, dict):
                    registry.skills[name] = fn
                loaded.append(name)
        except Exception as exc:
            logger.warning("custom skill load failed %s: %s", path, exc)
    return loaded
