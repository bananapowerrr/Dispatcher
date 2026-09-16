# -*- coding: utf-8 -*-
"""Task safety policies: git branch isolation + diff budget.

Phase E (ROADMAP_STABILITY):
  - Autopilot / high complexity → prefer isolated branch
  - Cap files/lines a single task may change before we refuse commit
"""
from __future__ import annotations

import os
from typing import Any


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)) or default)
    except (TypeError, ValueError):
        return default


# Defaults: generous for UI, tighter for autopilot
DIFF_MAX_FILES = _env_int("AGENTBUS_DIFF_MAX_FILES", 25)
DIFF_MAX_LINES = _env_int("AGENTBUS_DIFF_MAX_LINES", 2000)
DIFF_MAX_FILES_AUTO = _env_int("AGENTBUS_DIFF_MAX_FILES_AUTO", 12)
DIFF_MAX_LINES_AUTO = _env_int("AGENTBUS_DIFF_MAX_LINES_AUTO", 800)


def task_source(task: Any) -> str:
    meta = {}
    if isinstance(task, dict):
        meta = task.get("metadata") if isinstance(task.get("metadata"), dict) else {}
        return str(meta.get("source") or task.get("source") or "").lower()
    meta = getattr(task, "metadata", None) or {}
    if isinstance(meta, dict):
        return str(meta.get("source") or "").lower()
    return ""


def task_complexity(task: Any) -> int:
    meta: dict = {}
    if isinstance(task, dict):
        meta = task.get("metadata") if isinstance(task.get("metadata"), dict) else {}
        for src in (task, meta):
            try:
                c = int(src.get("complexity") or 0)
                if 1 <= c <= 5:
                    return c
            except (TypeError, ValueError, AttributeError):
                pass
        return 2
    meta = getattr(task, "metadata", None) or {}
    if isinstance(meta, dict):
        try:
            c = int(meta.get("complexity") or 0)
            if 1 <= c <= 5:
                return c
        except (TypeError, ValueError):
            pass
    try:
        c = int(getattr(task, "complexity", None) or 0)
        if 1 <= c <= 5:
            return c
    except (TypeError, ValueError):
        pass
    return 2


def resolve_git_policy(task: Any, default: str = "park") -> str:
    """Choose dirty-git policy for this task.

    Autopilot / night / complexity >= 4 → branch isolation when default is park.
    Explicit metadata.git_policy wins.
    """
    meta = {}
    if isinstance(task, dict):
        meta = task.get("metadata") if isinstance(task.get("metadata"), dict) else {}
    else:
        meta = getattr(task, "metadata", None) or {}
        if not isinstance(meta, dict):
            meta = {}
    explicit = str(meta.get("git_policy") or "").strip().lower()
    if explicit in ("park", "stash", "branch", "allow"):
        return explicit

    src = task_source(task)
    c = task_complexity(task)
    force_branch = src in {"autopilot", "night", "night_scheduler"} or c >= 4
    base = (default or "park").strip().lower()
    if force_branch and base in ("park", "stash", ""):
        return "branch"
    return base or "park"


def diff_limits_for_task(task: Any) -> tuple[int, int]:
    """Return (max_files, max_lines) for this task."""
    src = task_source(task)
    if src in {"autopilot", "night", "night_scheduler"}:
        return DIFF_MAX_FILES_AUTO, DIFF_MAX_LINES_AUTO
    c = task_complexity(task)
    if c >= 4:
        return max(8, DIFF_MAX_FILES // 2), max(400, DIFF_MAX_LINES // 2)
    return DIFF_MAX_FILES, DIFF_MAX_LINES


def count_diff_lines(root: str, paths: list[str]) -> int:
    """Best-effort numstat sum for paths (insertions+deletions)."""
    if not paths:
        return 0
    import subprocess
    from pathlib import Path

    root_p = Path(root)
    total = 0
    try:
        r = subprocess.run(
            ["git", "diff", "--numstat", "HEAD", "--", *paths],
            cwd=str(root_p),
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        for line in (r.stdout or "").splitlines():
            parts = line.split("\t")
            if len(parts) < 3:
                continue
            a, b = parts[0], parts[1]
            if a.isdigit():
                total += int(a)
            if b.isdigit():
                total += int(b)
    except Exception:
        return total
    # untracked: approximate with file size in lines
    try:
        r2 = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard", "-z"],
            cwd=str(root_p),
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        untracked = {p for p in (r2.stdout or "").split("\0") if p}
        for p in paths:
            if p in untracked:
                fp = root_p / p
                if fp.is_file():
                    try:
                        total += sum(1 for _ in fp.open("r", encoding="utf-8", errors="ignore"))
                    except OSError:
                        pass
    except Exception:
        pass
    return total


def check_diff_budget(
    *,
    root: str,
    stage_paths: list[str],
    task: Any,
) -> dict[str, Any]:
    """Return {ok, reason, files, lines, max_files, max_lines}."""
    max_files, max_lines = diff_limits_for_task(task)
    files = list(stage_paths or [])
    n_files = len(files)
    n_lines = count_diff_lines(root, files) if files else 0
    out: dict[str, Any] = {
        "ok": True,
        "reason": "",
        "files": n_files,
        "lines": n_lines,
        "max_files": max_files,
        "max_lines": max_lines,
    }
    if n_files > max_files:
        out["ok"] = False
        out["reason"] = (
            f"diff budget exceeded: {n_files} files > max {max_files} "
            f"(source={task_source(task) or 'ui'})"
        )
        return out
    if n_lines > max_lines:
        out["ok"] = False
        out["reason"] = (
            f"diff budget exceeded: ~{n_lines} lines > max {max_lines} "
            f"(source={task_source(task) or 'ui'})"
        )
        return out
    return out
