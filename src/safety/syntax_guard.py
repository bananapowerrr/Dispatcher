# -*- coding: utf-8 -*-
"""Syntax Guard — reject broken Python before pytest/git commit.

7B models occasionally emit incomplete files. Catch SyntaxError early and
return a structured error for self-correction / verify_retry_message.
"""
from __future__ import annotations

import ast
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


def syntax_guard_enabled() -> bool:
    return os.getenv("AGENTBUS_SYNTAX_GUARD", "1").strip().lower() not in (
        "0", "false", "no", "off",
    )


@dataclass
class SyntaxIssue:
    path: str
    message: str
    lineno: int | None = None
    offset: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "message": self.message,
            "lineno": self.lineno,
            "offset": self.offset,
        }

    def format(self) -> str:
        loc = f":{self.lineno}" if self.lineno else ""
        return f"{self.path}{loc}: {self.message}"


@dataclass
class SyntaxReport:
    ok: bool
    issues: list[SyntaxIssue] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "issues": [i.to_dict() for i in self.issues],
        }

    def error_text(self) -> str:
        if self.ok:
            return ""
        lines = ["SyntaxError in changed files:"]
        for i in self.issues:
            lines.append(f"  - {i.format()}")
        lines.append("Fix syntax only; do not change unrelated code.")
        return "\n".join(lines)


def check_source(source: str, path: str = "<string>") -> SyntaxIssue | None:
    try:
        ast.parse(source, filename=path)
        return None
    except SyntaxError as exc:
        return SyntaxIssue(
            path=path,
            message=str(exc.msg or exc),
            lineno=exc.lineno,
            offset=exc.offset,
        )


def check_file(path: str | Path) -> SyntaxIssue | None:
    p = Path(path)
    if not p.is_file() or p.suffix.lower() not in (".py", ".pyi"):
        return None
    try:
        src = p.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return SyntaxIssue(path=str(p), message=f"read error: {exc}")
    return check_source(src, str(p))


def check_paths(paths: list[str | Path], *, root: str | Path | None = None) -> SyntaxReport:
    """Parse all .py paths; resolve relative to root when needed."""
    issues: list[SyntaxIssue] = []
    base = Path(root) if root else None
    for raw in paths or []:
        p = Path(raw)
        if not p.is_file() and base is not None:
            cand = base / p
            if cand.is_file():
                p = cand
        if not p.is_file():
            continue
        if p.suffix.lower() not in (".py", ".pyi"):
            continue
        issue = check_file(p)
        if issue:
            issues.append(issue)
    return SyntaxReport(ok=not issues, issues=issues)


def guard_or_error(
    paths: list[str | Path],
    *,
    root: str | Path | None = None,
) -> tuple[bool, str]:
    """Convenience for runtime: (ok, error_message)."""
    if not syntax_guard_enabled():
        return True, ""
    report = check_paths(paths, root=root)
    if report.ok:
        return True, ""
    return False, report.error_text()
