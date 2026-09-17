# -*- coding: utf-8 -*-
"""FC-46: saved workspace layouts (panel visibility + mode) in ui.yaml."""
from __future__ import annotations

from pathlib import Path
from typing import Any


def _ui_path(root: Path | None = None) -> Path:
    if root is None:
        try:
            from core.config import BASE_DIR
            root = Path(BASE_DIR)
        except Exception:
            root = Path.cwd()
    return Path(root) / "config" / "ui.yaml"


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        import yaml
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_yaml(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        import yaml
        path.write_text(
            yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
    except Exception:
        # minimal fallback
        import json
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def get_layout(root: Path | None = None) -> dict[str, Any]:
    data = _load_yaml(_ui_path(root))
    layout = data.get("layout") if isinstance(data.get("layout"), dict) else {}
    mode = str(data.get("workspace_mode") or layout.get("mode") or "agent")
    return {
        "mode": mode,
        "left_width": int(layout.get("left_width") or 260),
        "right_width": int(layout.get("right_width") or 360),
        "show_left": bool(layout.get("show_left", True)),
        "show_right": bool(layout.get("show_right", True)),
        "preset": str(layout.get("preset") or mode),
    }


def save_layout(
    *,
    mode: str | None = None,
    left_width: int | None = None,
    right_width: int | None = None,
    show_left: bool | None = None,
    show_right: bool | None = None,
    preset: str | None = None,
    root: Path | None = None,
) -> dict[str, Any]:
    path = _ui_path(root)
    data = _load_yaml(path)
    layout = data.get("layout") if isinstance(data.get("layout"), dict) else {}
    if mode is not None:
        data["workspace_mode"] = mode
        layout["mode"] = mode
    if left_width is not None:
        layout["left_width"] = int(left_width)
    if right_width is not None:
        layout["right_width"] = int(right_width)
    if show_left is not None:
        layout["show_left"] = bool(show_left)
    if show_right is not None:
        layout["show_right"] = bool(show_right)
    if preset is not None:
        layout["preset"] = str(preset)
    data["layout"] = layout
    _save_yaml(path, data)
    return get_layout(root)


def apply_layout_preset(preset: str, root: Path | None = None) -> dict[str, Any]:
    """Named presets → mode + side visibility."""
    p = (preset or "agent").lower().strip()
    mapping = {
        "code": {"mode": "code", "show_left": True, "show_right": True},
        "agent": {"mode": "agent", "show_left": True, "show_right": True},
        "project": {"mode": "project", "show_left": True, "show_right": True},
        "chat": {"mode": "agent", "show_left": False, "show_right": False},
        "focus": {"mode": "code", "show_left": False, "show_right": False},
        "full": {"mode": "full", "show_left": True, "show_right": True},
    }
    cfg = mapping.get(p) or mapping["agent"]
    return save_layout(
        mode=cfg["mode"],
        show_left=cfg["show_left"],
        show_right=cfg["show_right"],
        preset=p,
        root=root,
    )


def list_layout_presets() -> list[dict[str, str]]:
    return [
        {"id": "agent", "label": "Agent (chat + queue)"},
        {"id": "code", "label": "Code (editor focus)"},
        {"id": "project", "label": "Project center"},
        {"id": "chat", "label": "Chat only"},
        {"id": "focus", "label": "Focus (editor only)"},
        {"id": "full", "label": "Full IDE"},
    ]
