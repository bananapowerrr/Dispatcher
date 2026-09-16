# -*- coding: utf-8 -*-
"""Готовые сценарии (рецепты) — ценность в первые 5 минут."""
from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any


def _root() -> Path:
    try:
        from core.config import BASE_DIR
        return Path(BASE_DIR)
    except Exception:
        return Path(__file__).resolve().parents[2]


def recipes_dir(root: Path | None = None) -> Path:
    return (root or _root()) / "recipes"


def list_recipes(root: Path | None = None) -> list[dict[str, Any]]:
    d = recipes_dir(root)
    out: list[dict[str, Any]] = []
    if not d.is_dir():
        return out
    for p in sorted(d.glob("*.json")):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                data["_path"] = str(p)
                out.append(data)
        except Exception:
            continue
    return out


def resolve_recipe(name: str, root: Path | None = None) -> dict[str, Any] | None:
    """name: refactor | tests | bugfix | filename stem | path."""
    key = (name or "").strip().lower().replace(".json", "")
    aliases = {
        "refactor": "01_refactor",
        "tests": "02_test_coverage",
        "test": "02_test_coverage",
        "coverage": "02_test_coverage",
        "bugfix": "03_bugfix",
        "bug": "03_bugfix",
        "fix": "03_bugfix",
        "docs": "04_docstrings",
        "doc": "04_docstrings",
        "docstrings": "04_docstrings",
        "types": "05_types",
        "typing": "05_types",
        "hints": "05_types",
        "explain": "06_explain",
        "explain_code": "06_explain",
    }
    stem = aliases.get(key, key)
    d = recipes_dir(root)
    for cand in (d / f"{stem}.json", d / f"{key}.json", Path(name)):
        if cand.is_file():
            try:
                data = json.loads(cand.read_text(encoding="utf-8"))
                return data if isinstance(data, dict) else None
            except Exception:
                return None
    # substring match
    for p in sorted(d.glob("*.json")):
        if stem in p.stem.lower() or key in p.stem.lower():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                continue
    return None


def emit_recipe(
    name: str,
    *,
    target: str | None = None,
    project: str = "",
    channel: str = "gpt",
    root: Path | None = None,
) -> Path:
    """Enqueue recipe via desktop_queue; optional phone file-bus mirror."""
    root = root or _root()
    recipe = resolve_recipe(name, root)
    if not recipe:
        raise FileNotFoundError(f"Рецепт не найден: {name}")

    files: list[str] = list(recipe.get("files") or [])
    if target:
        files = [target] + [f for f in files if f != target]

    task_id = f"recipe-{uuid.uuid4().hex[:10]}"
    meta = dict(recipe.get("metadata") or {})
    meta["source"] = meta.get("source") or "recipe"
    meta["recipe"] = name

    message = str(recipe.get("message") or "")
    if target and target not in message:
        message = f"{message}\n\nЦелевой файл/модуль: {target}"

    payload = {
        "id": task_id,
        "project": project or recipe.get("project") or "",
        "message": message,
        "files": files,
        "channel": channel,
        "status": "PENDING",
        "metadata": meta,
    }

    # Primary: desktop queue (PC product path)
    payload["channel"] = "desktop"
    payload.setdefault("metadata", {})["source"] = "recipe"
    payload.setdefault("metadata", {})["primary_channel"] = "desktop"
    try:
        from core.local_queue import get_local_queue
        tid = get_local_queue(root).put(payload)
        if tid:
            task_id = str(tid)
            payload["id"] = task_id
    except Exception as exc:
        raise RuntimeError(f"desktop_queue put failed: {exc}") from exc

    # Receipt path for CLI/UI status (spill dir)
    receipt = root / ".agentbus" / "desktop_queue" / f"{task_id}.json"
    receipt.parent.mkdir(parents=True, exist_ok=True)
    # spill may already have the file from LocalQueue; ensure readable receipt
    if not receipt.is_file():
        try:
            receipt.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError:
            pass

    # Optional phone file-bus mirror only
    try:
        from core.feature_flags import is_enabled
        if is_enabled("phone_filebus", default=False) or is_enabled("remote_filebus", default=False):
            path = root / "channels" / channel / "incoming" / f"{task_id}.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            mirror = dict(payload)
            mirror["channel"] = channel
            mirror.setdefault("metadata", {})["mirrored_from"] = "recipe_desktop"
            path.write_text(json.dumps(mirror, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass
    return receipt
