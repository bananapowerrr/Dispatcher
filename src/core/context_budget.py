# -*- coding: utf-8 -*-
"""DEV-005 / R5 Context Budget — 7B-friendly worker prompt assembly.

Order of blocks (priority when truncating):
  1. USER REQUEST
  2. CONSTRAINTS / previous failure
  3. RELEVANT FILES list (prioritized)
  4. FILE EXCERPTS
  5. optional MEMORY tails

context_audit logs what actually went to the worker.
"""
from __future__ import annotations

from typing import Any

DEFAULT_TOTAL_CHARS = 12_000
MIN_USER_CHARS = 400
MAX_FAILURE_CHARS = 1_200
MAX_CONSTRAINTS_CHARS = 800
MAX_FILE_LIST_CHARS = 1_000
DEFAULT_EXCERPT_BUDGET = 6_000

_TEST_HINTS = ("test_", "_test", "/tests/", "spec.")
_DOC_HINTS = (".md", ".rst", "docs/", "readme")
_UI_HINTS = ("ui/", "frontend/", "chat_panel", "settings_panel")


def clamp_text(text: str, max_chars: int, *, head_ratio: float = 0.55) -> str:
    s = str(text or "")
    if max_chars <= 0 or len(s) <= max_chars:
        return s
    if max_chars < 40:
        return s[:max_chars]
    head = int(max_chars * head_ratio)
    tail = max_chars - head - 20
    if tail < 10:
        return s[: max_chars - 1] + "…"
    return s[:head] + "\n…[truncated]…\n" + s[-tail:]


def prioritize_files(
    files: list[str],
    *,
    message: str = "",
    max_files: int = 12,
) -> list[str]:
    """Deterministic ranking: message hits > code > tests > ui > docs."""
    msg = str(message or "").lower()
    scored: list[tuple[int, int, str]] = []
    for i, f in enumerate(files or []):
        path = str(f).replace("\\", "/")
        low = path.lower()
        score = 50
        base = path.rsplit("/", 1)[-1].lower()
        if base and base in msg:
            score -= 30
        if any(h in low for h in _TEST_HINTS):
            score += 15
        if any(h in low for h in _DOC_HINTS):
            score += 25
        if any(h in low for h in _UI_HINTS):
            score += 10
        for part in path.split("/"):
            if len(part) > 3 and part.lower() in msg:
                score -= 5
        scored.append((score, i, path))
    scored.sort(key=lambda x: (x[0], x[1]))
    return [p for _, _, p in scored[: max(1, int(max_files or 12))]]


def build_context_budget_plan(
    *,
    total_chars: int = DEFAULT_TOTAL_CHARS,
    has_failure: bool = False,
    n_files: int = 0,
    include_memory: bool = False,
) -> dict[str, int]:
    total = max(2000, int(total_chars or DEFAULT_TOTAL_CHARS))
    user = max(MIN_USER_CHARS, min(3000, total // 5))
    failure = MAX_FAILURE_CHARS if has_failure else 0
    constraints = MAX_CONSTRAINTS_CHARS
    file_list = min(MAX_FILE_LIST_CHARS, 80 * max(1, n_files))
    used = user + failure + constraints + file_list
    rest = max(500, total - used)
    memory = min(1500, rest // 5) if include_memory else 0
    excerpts = max(800, rest - memory)
    return {
        "total": total,
        "user": user,
        "failure": failure,
        "constraints": constraints,
        "file_list": file_list,
        "excerpts": excerpts,
        "memory": memory,
    }


def build_context_audit(
    *,
    selected_files: list[str],
    excluded_files: list[str] | None = None,
    plan: dict[str, int] | None = None,
    chars: int = 0,
    truncated: bool = False,
    previous_failure: bool = False,
) -> dict[str, Any]:
    return {
        "selected_files": list(selected_files or [])[:40],
        "excluded_files": list(excluded_files or [])[:40],
        "selected_n": len(selected_files or []),
        "excluded_n": len(excluded_files or []),
        "plan": dict(plan or {}),
        "chars": int(chars or 0),
        "truncated": bool(truncated),
        "has_previous_failure": bool(previous_failure),
    }


def format_file_list(files: list[str], *, max_chars: int = MAX_FILE_LIST_CHARS) -> str:
    lines = ["Relevant files:"]
    for f in files or []:
        lines.append(f"  - {f}")
    return clamp_text("\n".join(lines), max_chars)


def format_constraints(items: list[str], *, max_chars: int = MAX_CONSTRAINTS_CHARS) -> str:
    items = [str(x).strip() for x in (items or []) if str(x).strip()]
    if not items:
        return ""
    body = "Constraints:\n" + "\n".join(f"  - {x}" for x in items)
    return clamp_text(body, max_chars)


def format_previous_failure(text: str, *, max_chars: int = MAX_FAILURE_CHARS) -> str:
    t = str(text or "").strip()
    if not t:
        return ""
    return clamp_text("Previous failure:\n" + t, max_chars)


def assemble_worker_message(
    *,
    user_message: str = "",
    files: list[str] | None = None,
    constraints: list[str] | None = None,
    previous_failure: str = "",
    file_excerpts: str = "",
    memory_block: str = "",
    total_chars: int = DEFAULT_TOTAL_CHARS,
    system_note: str = "",
    max_files: int = 12,
    all_files: list[str] | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Build worker message under budget. Returns context_audit."""
    if not user_message and kwargs.get("user_request"):
        user_message = str(kwargs.get("user_request") or "")
    if kwargs.get("memory") and not memory_block:
        memory_block = str(kwargs.get("memory") or "")
    raw_files = list(all_files or files or [])
    selected = prioritize_files(raw_files, message=user_message, max_files=max_files)
    excluded = [f for f in raw_files if f not in selected]
    plan = build_context_budget_plan(
        total_chars=total_chars,
        has_failure=bool(str(previous_failure or "").strip()),
        n_files=len(selected),
        include_memory=bool(str(memory_block or "").strip()),
    )
    parts: list[str] = []
    if str(system_note or "").strip():
        parts.append(clamp_text("SYSTEM:\n" + system_note.strip(), 1500))
    user = clamp_text(str(user_message or "").strip() or "(empty request)", plan["user"])
    parts.append("USER REQUEST:\n" + user)
    fail = format_previous_failure(previous_failure, max_chars=plan["failure"])
    if fail:
        parts.append(fail)
    cons = format_constraints(list(constraints or []), max_chars=plan["constraints"])
    if cons:
        parts.append(cons)
    if selected:
        parts.append(format_file_list(selected, max_chars=plan["file_list"]))
    excerpts = clamp_text(str(file_excerpts or "").strip(), plan["excerpts"])
    if excerpts:
        parts.append("FILE EXCERPTS:\n" + excerpts)
    mem = clamp_text(str(memory_block or "").strip(), plan["memory"])
    if mem:
        parts.append(mem)
    message = "\n\n".join(parts).strip()
    truncated = len(message) > plan["total"]
    if truncated:
        message = clamp_text(message, plan["total"])
    audit = build_context_audit(
        selected_files=selected,
        excluded_files=excluded,
        plan=plan,
        chars=len(message),
        truncated=truncated,
        previous_failure=bool(str(previous_failure or "").strip()),
    )
    return {
        "message": message,
        "plan": plan,
        "truncated": truncated,
        "chars": len(message),
        "files_n": len(selected),
        "context_audit": audit,
        "selected_files": list(selected),
        "excluded_files": list(excluded),
    }


def budget_from_context_report(
    report: Any,
    *,
    user_message: str,
    previous_failure: str = "",
    file_excerpts: str = "",
    total_chars: int = DEFAULT_TOTAL_CHARS,
) -> dict[str, Any]:
    files: list[str] = []
    constraints: list[str] = []
    if report is not None:
        files = list(getattr(report, "relevant_files", None) or [])
        if not files and isinstance(report, dict):
            files = list(report.get("relevant_files") or [])
        constraints = list(getattr(report, "constraints", None) or [])
        if not constraints and isinstance(report, dict):
            constraints = list(report.get("constraints") or [])
    return assemble_worker_message(
        user_message=user_message,
        files=files,
        constraints=constraints,
        previous_failure=previous_failure,
        file_excerpts=file_excerpts,
        total_chars=total_chars,
    )
