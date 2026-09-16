# -*- coding: utf-8 -*-
"""Worker presets: filter/boost workers from config/presets/*.yaml."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

from core.config import BASE_DIR


def _presets_dir() -> Path:
    env = (os.getenv("AGENTBUS_PRESETS_DIR") or "").strip()
    if env:
        return Path(env)
    return BASE_DIR / "config" / "presets"


def list_presets() -> list[str]:
    d = _presets_dir()
    if not d.is_dir():
        return []
    return sorted(p.stem for p in d.glob("*.yaml"))


def load_preset(name: str | None = None) -> dict[str, Any]:
    """Load preset by name or AGENTBUS_PRESET / ui.yaml active_preset."""
    if not name:
        name = (os.getenv("AGENTBUS_PRESET") or "").strip()
    if not name:
        # ui.yaml
        try:
            ui = BASE_DIR / "config" / "ui.yaml"
            if ui.is_file():
                data = yaml.safe_load(ui.read_text(encoding="utf-8")) or {}
                name = str(data.get("active_preset") or "").strip()
        except Exception:
            name = ""
    if not name:
        return {}
    path = _presets_dir() / f"{name}.yaml"
    if not path.is_file():
        return {}
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if isinstance(raw, dict) and "preset" in raw:
            preset = raw["preset"]
            return preset if isinstance(preset, dict) else {}
        return raw if isinstance(raw, dict) else {}
    except Exception:
        return {}


def apply_preset(workers: list[Any], preset: dict[str, Any] | None = None) -> list[Any]:
    """Return filtered/boosted copy of workers list (does not mutate originals)."""
    if preset is None:
        preset = load_preset()
    if not preset:
        return list(workers)

    allow_w = {str(x) for x in (preset.get("allow_workers") or [])}
    allow_p = {str(x) for x in (preset.get("allow_providers") or [])}
    boost = preset.get("priority_boost") or {}
    if not isinstance(boost, dict):
        boost = {}
    timeout_cap = preset.get("timeout_cap")
    timeout_floor = preset.get("timeout_floor")

    out: list[Any] = []
    for w in workers:
        name = getattr(w, "name", "") or ""
        provider = getattr(w, "provider", "") or ""
        if allow_w and name not in allow_w:
            continue
        if allow_p and provider not in allow_p:
            continue
        # shallow clone via dataclass replace if possible
        try:
            from dataclasses import replace
            nw = replace(w)
        except Exception:
            nw = w
        if name in boost:
            try:
                nw.priority = int(getattr(nw, "priority", 50) or 50) + int(boost[name])
            except Exception:
                pass
        if timeout_cap is not None:
            try:
                nw.timeout = min(int(getattr(nw, "timeout", 600) or 600), int(timeout_cap))
            except Exception:
                pass
        if timeout_floor is not None:
            try:
                nw.timeout = max(int(getattr(nw, "timeout", 600) or 600), int(timeout_floor))
            except Exception:
                pass
        out.append(nw)
    return out if out else list(workers)
