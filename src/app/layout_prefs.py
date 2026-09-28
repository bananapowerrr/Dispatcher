# -*- coding: utf-8 -*-
"""FC-46: saved workspace layouts (panel visibility + mode) in ui.yaml."""
from __future__ import annotations

from pathlib import Path
from typing import Any


def _ui_path(root: Path | None = None) -> Path:
    # Чтение идёт через ui_config: defaults + локальные переопределения.
    from app.ui_config import ui_defaults_path
    return ui_defaults_path(root)


def _load_cfg(root: Path | None = None) -> dict[str, Any]:
    from app.ui_config import load_ui_cfg
    return load_ui_cfg(root)


def _save_yaml(path: Path, data: dict[str, Any], root: Path | None = None) -> None:
    # Раньше писали прямо в config/ui.yaml полным safe_dump: это выжигало
    # комментарии шаблона и затирало чужие ключи. Теперь — merge в
    # .agentbus/ui.yaml через единый писатель.
    # root обязателен: иначе запись уйдёт в реальный проект, а не в переданный.
    from app.ui_config import update_ui_cfg
    target_root = root if root is not None else path.parent.parent
    update_ui_cfg(data, target_root)


def get_layout(root: Path | None = None) -> dict[str, Any]:
    data = _load_cfg(root)
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
    data = _load_cfg(root)
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
    _save_yaml(path, data, root)
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
