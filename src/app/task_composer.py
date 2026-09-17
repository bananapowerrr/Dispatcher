# -*- coding: utf-8 -*-
"""FC-47: Task Composer — build a valid task payload from UI fields.

Does not execute workers; only normalizes into intake-ready dict.
"""
from __future__ import annotations

import time
import uuid
from pathlib import Path
from typing import Any


def compose_task(
    *,
    message: str,
    project: str | Path | None = None,
    files: list[str] | None = None,
    priority: int | None = None,
    channel: str = "desktop",
    force_refresh: bool = False,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return task dict suitable for LocalQueue / file-bus incoming."""
    msg = (message or "").strip()
    if not msg:
        raise ValueError("message is required")
    tid = f"ui-{uuid.uuid4().hex[:12]}"
    files = [str(f).strip() for f in (files or []) if str(f).strip()]
    meta = dict(metadata or {})
    meta.setdefault("source", "task_composer")
    meta.setdefault("created_at", time.time())
    task: dict[str, Any] = {
        "id": tid,
        "message": msg,
        "files": files,
        "channel": channel or "desktop",
        "force_refresh": bool(force_refresh),
        "metadata": meta,
    }
    if project:
        task["project"] = str(project)
    if priority is not None:
        task["priority"] = int(priority)
    return task


def compose_from_suggestion(
    agent_service: Any,
    index: int = 0,
    *,
    project: str | Path | None = None,
) -> dict[str, Any]:
    """Compose task from AgentService.suggestion_prompt."""
    prompt = ""
    try:
        prompt = agent_service.suggestion_prompt(index)
    except Exception:
        prompt = ""
    if not prompt:
        raise ValueError("no suggestion available")
    root = project or getattr(agent_service, "root", None)
    files = []
    af = getattr(agent_service, "active_file", "") or ""
    if af:
        files.append(af)
    return compose_task(message=prompt, project=root, files=files)


def validate_task_dict(task: dict[str, Any]) -> list[str]:
    """Light validation; full contract stays in task_contract at intake."""
    errs: list[str] = []
    if not (task.get("message") or "").strip():
        errs.append("empty message")
    if not task.get("id"):
        errs.append("missing id")
    return errs


def format_composer_preview(task: dict[str, Any]) -> str:
    lines = [
        f"id: {task.get('id')}",
        f"project: {task.get('project') or '—'}",
        f"files: {', '.join(task.get('files') or []) or '—'}",
        f"channel: {task.get('channel')}",
        "",
        str(task.get("message") or ""),
    ]
    return "\n".join(lines)
