# -*- coding: utf-8 -*-
"""Post-mortem for quarantined tasks — lessons without poisoning MEMORY.

Writes structured notes under .agentbus/lessons/ and optional lesson_learner hook.
Does NOT auto-append to MEMORY.md (operator/threshold later).
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


def analyze_failure(
    *,
    task: dict[str, Any],
    error: str = "",
    verify_output: str = "",
) -> dict[str, Any]:
    """Heuristic post-mortem (no LLM). Returns structured lesson dict."""
    err = (error or verify_output or "").lower()
    category = "unknown"
    tip = "Review diff and verify output."
    if "syntax" in err or "syntaxerror" in err:
        category = "syntax"
        tip = "Model emitted invalid Python; prefer smaller file scope and re-prompt."
    elif "staticguard" in err or "bare_except" in err or "eval" in err:
        category = "static"
        tip = "Anti-pattern rejected pre-pytest; ban bare except/eval in system prompt."
    elif "pytest" in err or "assertion" in err or "failed" in err:
        category = "test"
        tip = "Tests failed; fix logic not only syntax; avoid weakening asserts."
    elif "timeout" in err or "тайм-аут" in err:
        category = "timeout"
        tip = "Worker timeout; raise EXEC_HARD_CAP only if stream heartbeat is healthy."
    elif "diff budget" in err:
        category = "diff_budget"
        tip = "Change set too large; decompose task."
    return {
        "category": category,
        "tip": tip,
        "task_id": task.get("id"),
        "message": (task.get("message") or "")[:300],
        "files": list(task.get("files") or [])[:20],
        "error_excerpt": (error or verify_output or "")[:800],
        "ts": time.time(),
    }


def write_lesson(
    bus_or_project_root: str | Path,
    analysis: dict[str, Any],
) -> Path | None:
    """Persist lesson JSON under .agentbus/lessons/."""
    root = Path(bus_or_project_root)
    lessons = root / ".agentbus" / "lessons"
    try:
        lessons.mkdir(parents=True, exist_ok=True)
    except OSError:
        return None
    tid = str(analysis.get("task_id") or "unknown")
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in tid)[:48]
    path = lessons / f"{time.strftime('%Y%m%d_%H%M%S')}_{safe}.json"
    try:
        path.write_text(
            json.dumps(analysis, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError:
        return None
    return path


def post_mortem_quarantine(
    root: str | Path,
    task: dict[str, Any],
    *,
    error: str = "",
) -> dict[str, Any]:
    """Full offline post-mortem pipeline for a quarantined task."""
    analysis = analyze_failure(task=task, error=error)
    path = write_lesson(root, analysis)
    # Soft hook into lesson_learner if present
    try:
        from intelligence.lesson_learner import GLOBAL_LEARNER  # type: ignore

        if GLOBAL_LEARNER is not None and hasattr(GLOBAL_LEARNER, "record"):
            GLOBAL_LEARNER.record(
                task,
                success=False,
                error=error,
                category=analysis.get("category"),
            )
    except Exception:
        pass
    return {"analysis": analysis, "lesson_path": str(path) if path else ""}
