# -*- coding: utf-8 -*-
"""Day-15: deterministic project context report (no RAG / embeddings).

Human-readable summary for chat, doctor, or pre-worker diagnostics:

  Project / Task / Git dirty / Relevant files / Tests / Constraints / Size

Uses intelligence.file_selector only. Does not touch FSM / intake / executor.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)) or default)
    except ValueError:
        return default


DEFAULT_MAX_FILES = _env_int("AGENTBUS_CTX_MAX_FILES", 6)


@dataclass
class ContextReport:
    project: str = ""
    project_root: str = ""
    task: str = ""
    git_dirty: list[str] = field(default_factory=list)
    relevant_files: list[str] = field(default_factory=list)
    reasons: dict[str, str] = field(default_factory=dict)
    tests: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    context_size: dict[str, Any] = field(default_factory=dict)
    stats: dict[str, Any] = field(default_factory=dict)
    ok: bool = True
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "project": self.project,
            "project_root": self.project_root,
            "task": self.task,
            "git_dirty": list(self.git_dirty),
            "relevant_files": list(self.relevant_files),
            "reasons": dict(self.reasons),
            "tests": list(self.tests),
            "constraints": list(self.constraints),
            "context_size": dict(self.context_size),
            "stats": dict(self.stats),
            "notes": list(self.notes),
        }

    def format_text(self, *, max_chars: int = 2500) -> str:
        """Deterministic multi-line report for chat / logs."""
        lines: list[str] = []
        lines.append(f"Project: {self.project or '(none)'}")
        if self.project_root:
            lines.append(f"Root: {self.project_root}")
        task = (self.task or "").strip()
        if task:
            one = task.replace("\n", " ")[:200]
            lines.append(f"Task: {one}")
        if self.git_dirty:
            lines.append("Changed (git):")
            for p in self.git_dirty[:12]:
                lines.append(f"  • {p}")
        elif self.ok and self.project_root:
            lines.append("Changed (git): (clean or unavailable)")
        if self.relevant_files:
            lines.append("Relevant files:")
            for p in self.relevant_files:
                why = self.reasons.get(p, "")
                suffix = f"  [{why}]" if why else ""
                lines.append(f"  • {p}{suffix}")
        else:
            lines.append("Relevant files: (none)")
        if self.tests:
            lines.append("Tests:")
            for p in self.tests:
                lines.append(f"  • {p}")
        if self.constraints:
            lines.append("Constraints:")
            for c in self.constraints:
                lines.append(f"  • {c}")
        cs = self.context_size
        if cs:
            parts = []
            if cs.get("files") is not None:
                parts.append(f"files={cs['files']}")
            if cs.get("chars") is not None:
                parts.append(f"chars≈{cs['chars']}")
            if cs.get("max_files") is not None:
                parts.append(f"max_files={cs['max_files']}")
            if parts:
                lines.append("Context size: " + ", ".join(parts))
        for n in self.notes:
            lines.append(f"Note: {n}")
        text = "\n".join(lines).strip()
        if len(text) > max_chars:
            text = text[: max_chars - 20] + "\n…[truncated]"
        return text


def _estimate_chars(root: Path, files: list[str], *, per_file_cap: int = 4000) -> int:
    total = 0
    for rel in files:
        try:
            p = root / rel
            if not p.is_file():
                continue
            raw = p.read_text(encoding="utf-8", errors="replace")
            total += min(len(raw), per_file_cap)
        except OSError:
            continue
    return total


def _split_tests(files: list[str], reasons: dict[str, str]) -> tuple[list[str], list[str]]:
    main: list[str] = []
    tests: list[str] = []
    for f in files:
        reason = (reasons.get(f) or "").lower()
        name = f.replace("\\", "/").lower()
        is_test = (
            reason == "related_test"
            or "/test" in name
            or name.startswith("test_")
            or name.endswith("_test.py")
            or "/tests/" in name
        )
        if is_test:
            tests.append(f)
        else:
            main.append(f)
    return main, tests


def build_context_report(
    *,
    project_root: str | Path | None = None,
    message: str = "",
    explicit_files: list[str] | None = None,
    max_files: int | None = None,
    constraints: list[str] | None = None,
    project_name: str | None = None,
) -> ContextReport:
    """Build deterministic context report from task message + project root.

    Safe with missing root / empty project: still returns a structured report.
    """
    max_n = max_files if max_files is not None else DEFAULT_MAX_FILES
    notes: list[str] = []
    root_s = ""
    root: Path | None = None
    name = (project_name or "").strip()

    if project_root:
        try:
            root = Path(project_root).resolve()
            root_s = str(root)
            if not name:
                name = root.name
            if not root.is_dir():
                notes.append("project root is not a directory")
                root = None
        except Exception as exc:
            notes.append(f"invalid project_root: {exc}")
            root = None
    else:
        notes.append("no project root")

    # selection (Day-7)
    try:
        from intelligence.file_selector import select_files_for_task, _git_dirty

        sel = select_files_for_task(
            project_root=root_s or None,
            message=message or "",
            explicit_files=explicit_files or [],
            max_files=max_n,
        )
        files = list(sel.files)
        reasons = dict(sel.reasons)
        stats = dict(sel.stats)
        dirty: list[str] = []
        if root is not None:
            try:
                dirty = list(_git_dirty(root))
            except Exception:
                dirty = []
    except Exception as exc:
        files, reasons, stats, dirty = [], {}, {"error": str(exc)}, []
        notes.append(f"file_selector failed: {exc}")

    main, tests = _split_tests(files, reasons)
    # keep full relevant list order (deterministic from selector)
    relevant = list(files)

    ctx_size: dict[str, Any] = {
        "files": len(relevant),
        "max_files": max_n,
    }
    if root is not None and relevant:
        ctx_size["chars"] = _estimate_chars(root, relevant)

    cons = [str(c).strip() for c in (constraints or []) if str(c).strip()]
    # soft defaults useful for 7B
    if max_n <= 8 and "prefer small context" not in " ".join(cons).lower():
        cons.append(f"max relevant files ≤ {max_n} (7B-friendly)")

    ok = root is not None and not any("failed" in n for n in notes)

    return ContextReport(
        project=name or "(none)",
        project_root=root_s,
        task=(message or "").strip(),
        git_dirty=dirty,
        relevant_files=relevant,
        reasons=reasons,
        tests=tests,
        constraints=cons,
        context_size=ctx_size,
        stats=stats,
        ok=ok,
        notes=notes,
    )


def format_context_report(
    *,
    project_root: str | Path | None = None,
    message: str = "",
    explicit_files: list[str] | None = None,
    max_files: int | None = None,
    constraints: list[str] | None = None,
    project_name: str | None = None,
    max_chars: int = 2500,
) -> str:
    """Convenience: build + format_text."""
    rep = build_context_report(
        project_root=project_root,
        message=message,
        explicit_files=explicit_files,
        max_files=max_files,
        constraints=constraints,
        project_name=project_name,
    )
    return rep.format_text(max_chars=max_chars)
