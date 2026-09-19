# -*- coding: utf-8 -*-
"""Pure helpers for phone file-bus status (no GUI)."""
from __future__ import annotations

from pathlib import Path


def channel_counts(root: Path) -> dict[str, dict[str, int]]:
    """Per-channel queue counts."""
    out: dict[str, dict[str, int]] = {}
    ch = root / "channels"
    if not ch.is_dir():
        return out
    for d in sorted(ch.iterdir()):
        if not d.is_dir():
            continue
        counts: dict[str, int] = {}
        for state in ("incoming", "processing", "done", "errors", "deferred"):
            p = d / state
            n = 0
            if p.is_dir():
                try:
                    n = sum(1 for f in p.iterdir() if f.is_file() and f.suffix == ".json")
                except OSError:
                    n = 0
            counts[state] = n
        out[d.name] = counts
    return out


def format_channel_status(counts: dict[str, dict[str, int]], *, enabled: bool) -> str:
    head = "Включён" if enabled else "Выключен (чат ПК — основной)"
    if not counts:
        return f"{head} · channels/ нет — создастся при первом запуске"
    parts = [head]
    for name, c in counts.items():
        parts.append(
            f"{name}: in={c.get('incoming', 0)} run={c.get('processing', 0)} "
            f"done={c.get('done', 0)} err={c.get('errors', 0)}"
        )
    return " · ".join(parts)
