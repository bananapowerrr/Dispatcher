# -*- coding: utf-8 -*-
"""Nightly Report: сводка автопилота за сессию."""
from __future__ import annotations
from datetime import datetime
from pathlib import Path
from typing import Any


class NightlyReport:
    def __init__(self, log: Any = None, report_dir: str | Path | None = None):
        self.log = log
        self.report_dir = Path(report_dir) if report_dir else None
        self.tasks_completed = 0
        self.tasks_failed = 0
        self.tasks_blocked = 0
        self.commits = 0
        self.executor_stats: dict[str, dict[str, int]] = {}
        self.executor_notes: dict[str, str] = {}

    def record(self, status: str, executor: str = "", attempts: int = 0) -> None:
        if status == "DONE":
            self.tasks_completed += 1
        elif status in ("ERROR", "BLOCKED"):
            if status == "BLOCKED":
                self.tasks_blocked += 1
            else:
                self.tasks_failed += 1
        if executor:
            st = self.executor_stats.setdefault(executor, {"attempts": 0, "success": 0})
            st["attempts"] += 1
            if status == "DONE":
                st["success"] += 1

    def note_executor(self, executor: str, note: str) -> None:
        self.executor_notes[executor] = note

    def render(self) -> str:
        lines = ["=" * 30, "NIGHTLY REPORT", "=" * 30]
        lines.append(f"Time: {datetime.now():%Y-%m-%d %H:%M}")
        lines.append(f"Tasks completed: {self.tasks_completed}")
        lines.append(f"Tasks failed:    {self.tasks_failed}")
        lines.append(f"Tasks blocked:   {self.tasks_blocked}")
        lines.append(f"Commits:         {self.commits}")
        lines.append("Executors:")
        for name, st in sorted(self.executor_stats.items()):
            note = "  " + (self.executor_notes.get(name) or "")
            lines.append(f"  {name:12} {st['success']}/{st['attempts']}{note}")
        return "\n".join(lines)

    def save(self, suffix: str = "") -> Path | None:
        if not self.report_dir:
            if self.log is not None and hasattr(self.log, "write"):
                self.log.write("NIGHTLY REPORT\n" + self.render())
            return None
        self.report_dir.mkdir(parents=True, exist_ok=True)
        name = f"nightly_{suffix}_{datetime.now():%Y%m%d_%H%M%S}.txt" if suffix \
            else f"nightly_{datetime.now():%Y%m%d_%H%M%S}.txt"
        path = self.report_dir / name
        path.write_text(self.render(), encoding="utf-8")
        return path
