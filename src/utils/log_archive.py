# -*- coding: utf-8 -*-
"""Archive old channel log files to .agentbus/archive/logs/."""
from __future__ import annotations

import shutil
import time
from pathlib import Path
from typing import Any


def archive_old_logs(
    bus_root: str | Path,
    *,
    max_age_days: float = 7.0,
    max_files_per_channel: int = 200,
) -> dict[str, Any]:
    """Move old logs under channels/*/logs to archive. Returns stats."""
    root = Path(bus_root)
    channels = root / "channels"
    archive = root / ".agentbus" / "archive" / "logs"
    archive.mkdir(parents=True, exist_ok=True)
    moved = 0
    skipped = 0
    cutoff = time.time() - max_age_days * 86400
    if not channels.is_dir():
        return {"moved": 0, "skipped": 0}
    for ch in channels.iterdir():
        log_dir = ch / "logs"
        if not log_dir.is_dir():
            continue
        files = sorted(
            [p for p in log_dir.iterdir() if p.is_file()],
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        for i, p in enumerate(files):
            try:
                mtime = p.stat().st_mtime
            except OSError:
                skipped += 1
                continue
            too_old = mtime < cutoff
            over_cap = i >= max_files_per_channel
            if not (too_old or over_cap):
                continue
            dest_dir = archive / ch.name
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest = dest_dir / p.name
            try:
                if dest.exists():
                    dest = dest_dir / f"{p.stem}_{int(mtime)}{p.suffix}"
                shutil.move(str(p), str(dest))
                moved += 1
            except OSError:
                skipped += 1
    return {"moved": moved, "skipped": skipped, "archive": str(archive)}


def prune_old_archives(
    bus_root: str | Path,
    *,
    max_age_days: float | None = None,
    max_files: int | None = None,
) -> dict[str, Any]:
    """Delete files under .agentbus/archive/ older than TTL (or over cap).

    Env: AGENTBUS_ARCHIVE_TTL_DAYS (default 14), AGENTBUS_ARCHIVE_MAX_FILES (default 500).
    """
    import os
    root = Path(bus_root)
    archive = root / ".agentbus" / "archive"
    if not archive.is_dir():
        return {"deleted": 0, "kept": 0, "reason": "no_archive"}
    if max_age_days is None:
        try:
            max_age_days = float(os.getenv("AGENTBUS_ARCHIVE_TTL_DAYS", "14") or "14")
        except (TypeError, ValueError):
            max_age_days = 14.0
    if max_files is None:
        try:
            max_files = int(os.getenv("AGENTBUS_ARCHIVE_MAX_FILES", "500") or "500")
        except (TypeError, ValueError):
            max_files = 500
    cutoff = time.time() - float(max_age_days) * 86400
    files: list[Path] = []
    for p in archive.rglob("*"):
        if p.is_file():
            files.append(p)
    deleted = 0
    kept = 0
    # age-based
    survivors: list[tuple[float, Path]] = []
    for p in files:
        try:
            mtime = p.stat().st_mtime
        except OSError:
            continue
        if mtime < cutoff:
            try:
                p.unlink()
                deleted += 1
            except OSError:
                survivors.append((mtime, p))
        else:
            survivors.append((mtime, p))
    # count cap: keep newest
    survivors.sort(key=lambda x: x[0], reverse=True)
    for i, (_mt, p) in enumerate(survivors):
        if i >= int(max_files):
            try:
                p.unlink()
                deleted += 1
            except OSError:
                kept += 1
        else:
            kept += 1
    # prune empty dirs
    for d in sorted(archive.rglob("*"), reverse=True):
        if d.is_dir():
            try:
                d.rmdir()
            except OSError:
                pass
    return {
        "deleted": deleted,
        "kept": kept,
        "archive": str(archive),
        "ttl_days": max_age_days,
        "max_files": max_files,
    }
