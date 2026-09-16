# -*- coding: utf-8 -*-
"""Lightweight terminal status board (no rich/textual dependency).

Shows queue depth per channel and key safety flags. Safe to call from diagnose
or occasionally from the dispatcher loop.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any


def _count_json(dir_path: Path) -> int:
    if not dir_path.is_dir():
        return 0
    n = 0
    try:
        for p in dir_path.iterdir():
            if p.is_file() and p.suffix == ".json" and not p.name.endswith(".lease.json"):
                n += 1
    except OSError:
        return 0
    return n


def channel_snapshot(bus_root: str | Path, channels: tuple[str, ...] | list[str]) -> list[dict[str, Any]]:
    root = Path(bus_root)
    rows = []
    for ch in channels:
        base = root / "channels" / ch
        rows.append({
            "channel": ch,
            "incoming": _count_json(base / "incoming"),
            "processing": _count_json(base / "processing"),
            "done": _count_json(base / "done"),
            "errors": _count_json(base / "errors"),
            "deferred": _count_json(base / "deferred"),
        })
    return rows


def safety_flags() -> dict[str, str]:
    return {
        "syntax_guard": os.getenv("AGENTBUS_SYNTAX_GUARD", "1"),
        "static_guard": os.getenv("AGENTBUS_STATIC_GUARD", "1"),
        "static_ruff": os.getenv("AGENTBUS_STATIC_RUFF", "0"),
        "max_parallel_projects": os.getenv("AGENTBUS_MAX_PARALLEL_PROJECTS", "1"),
        "exec_hard_cap": os.getenv("AGENTBUS_EXEC_HARD_CAP", "1800"),
        "stuck_timeout_max": os.getenv("AGENTBUS_STUCK_TIMEOUT_MAX", "1800"),
    }


def print_board(bus_root: str | Path | None = None, channels: tuple[str, ...] | list[str] | None = None) -> None:
    """Print a compact status table to stdout."""
    try:
        from core.config import BUS_ROOT, CHANNELS
        root = Path(bus_root or BUS_ROOT)
        chans = list(channels or CHANNELS)
    except Exception:
        root = Path(bus_root or ".")
        chans = list(channels or ("gpt", "autopilot"))

    print("\n--- status board ---")
    flags = safety_flags()
    print(
        "safety: "
        + " · ".join(f"{k}={v}" for k, v in flags.items())
    )
    rows = channel_snapshot(root, chans)
    if not rows:
        print("queues: (no channels)")
        return
    hdr = f"{'channel':12} {'in':>4} {'proc':>4} {'done':>4} {'err':>4} {'def':>4}"
    print(hdr)
    print("-" * len(hdr))
    for r in rows:
        print(
            f"{r['channel'][:12]:12} "
            f"{r['incoming']:4d} {r['processing']:4d} {r['done']:4d} "
            f"{r['errors']:4d} {r['deferred']:4d}"
        )
    # quarantine count
    qdir = root / ".agentbus" / "quarantine" / "tasks"
    qn = _count_json(qdir) if qdir.is_dir() else 0
    print(f"quarantine tasks : {qn}")
    lessons = root / ".agentbus" / "lessons"
    ln = _count_json(lessons) if lessons.is_dir() else 0
    print(f"post-mortem notes: {ln}")
    try:
        from utils.metrics import GLOBAL_METRICS
        c = getattr(GLOBAL_METRICS, "counters", None) or {}
        keys = (
            "llm_call", "llm_fail", "worker_fallback",
            "retry_budget_exhausted", "task_quarantined",
            "cache_hit", "skill_hit",
        )
        bits = [f"{k}={c.get(k, 0)}" for k in keys if k in c or True]
        # always show
        bits = []
        for k in keys:
            bits.append(f"{k}={int(c.get(k, 0) if isinstance(c, dict) else 0)}")
        print("metrics          : " + " · ".join(bits))
    except Exception:
        pass


def board_dict(bus_root: str | Path | None = None) -> dict[str, Any]:
    try:
        from core.config import BUS_ROOT, CHANNELS
        root = Path(bus_root or BUS_ROOT)
        chans = list(CHANNELS)
    except Exception:
        root = Path(bus_root or ".")
        chans = ["gpt"]
    return {
        "flags": safety_flags(),
        "queues": channel_snapshot(root, chans),
        "quarantine": _count_json(root / ".agentbus" / "quarantine" / "tasks"),
    }
