# -*- coding: utf-8 -*-
"""Tail AgentBus event JSONL for Terminal / UI (non-blocking)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


_OFFSETS: dict[str, int] = {}


def event_paths(project_root: str | Path | None = None) -> list[Path]:
    roots: list[Path] = []
    if project_root:
        roots.append(Path(project_root))
    try:
        from core.config import BASE_DIR
        roots.append(Path(BASE_DIR))
    except Exception:
        pass
    roots.append(Path.cwd())
    seen: set[str] = set()
    out: list[Path] = []
    for root in roots:
        for rel in (
            "eventbus.jsonl",
            ".agentbus/events.jsonl",
            "logs/events.jsonl",
            "eventbus/events.jsonl",
        ):
            p = (root / rel).resolve()
            key = str(p)
            if key in seen:
                continue
            seen.add(key)
            if p.is_file():
                out.append(p)
    return out


def drain_events(
    project_root: str | Path | None = None,
    *,
    max_lines: int = 40,
) -> list[dict[str, Any]]:
    """Return new events since last drain (best-effort)."""
    events: list[dict[str, Any]] = []
    for path in event_paths(project_root):
        key = str(path)
        try:
            data = path.read_bytes()
        except OSError:
            continue
        off = _OFFSETS.get(key, 0)
        if off > len(data):
            off = 0
        if off == 0 and len(data) > 200_000:
            # first open: start near end
            off = max(0, len(data) - 50_000)
        chunk = data[off:]
        _OFFSETS[key] = len(data)
        if not chunk:
            continue
        text = chunk.decode("utf-8", errors="replace")
        for line in text.splitlines():
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue
            if isinstance(obj, dict):
                events.append(obj)
    if len(events) > max_lines:
        events = events[-max_lines:]
    return events


def format_event_line(ev: dict[str, Any]) -> str:
    et = str(ev.get("type") or ev.get("event") or "MSG")
    tid = str(ev.get("task_id") or "")[:12]
    msg = str(ev.get("message") or ev.get("msg") or "")[:160]
    worker = str(ev.get("worker") or "")[:16]
    parts = [et]
    if tid:
        parts.append(tid)
    if worker:
        parts.append(worker)
    if msg:
        parts.append(msg)
    return " ".join(parts)


# Important types to surface in Terminal (noise filter)
IMPORTANT = frozenset({
    "CLAIM", "START", "READY", "DONE", "ERROR", "TIMEOUT", "RETRY",
    "TASK_DONE", "TASK_ERROR", "VERIFY_FAILED", "VERIFY_PASSED",
    "SKILL_HIT", "CACHE_HIT", "WORKER_SELECTED", "RECLAIM", "QUARANTINE",
    "LOOP", "RATE_LIMIT", "STATIC_FAIL", "SYNTAX_FAIL",
})


def filter_important(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for ev in events:
        et = str(ev.get("type") or ev.get("event") or "")
        if et in IMPORTANT or et.endswith("_FAIL") or et.endswith("_ERROR"):
            out.append(ev)
    return out
