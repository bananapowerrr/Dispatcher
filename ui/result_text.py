# -*- coding: utf-8 -*-
"""Human-readable task result strings for chat UI (no GUI deps).

FC-07: prefer TaskResult product contract when present; fall back to nested dict.
"""
from __future__ import annotations

from typing import Any


def extract_result_text(data: dict[str, Any] | None) -> str:
    """Flatten runtime done/error JSON into a short user-facing string.

    Runtime ``_save`` writes ``{**task.to_dict(), \"result\": {...}}`` where
    nested ``result`` is often a dict (worker, skill, error, stdout).
    When ``result.task_result`` is present, use ``TaskResult.format_human``.
    """
    if not isinstance(data, dict):
        return "готово"

    # Product contract first (FC-01…07)
    try:
        from core.task_result import build_task_result

        tr = build_task_result(data)
        human = tr.format_human()
        if human and (
            tr.verification
            or tr.changes.files
            or tr.error
            or tr.summary
            or tr.skill
            or tr.worker
        ):
            return human[:1200]
    except Exception:
        pass

    # FC-12: unified error humanizer when task failed
    try:
        st = str(data.get("status") or data.get("_state") or "").lower()
        nested0 = data.get("result") if isinstance(data.get("result"), dict) else {}
        failed = st in ("error", "errors", "failed") or (
            isinstance(nested0, dict) and nested0.get("ok") is False
        )
        if failed:
            from core.error_ux import humanize_from_row
            msg = humanize_from_row(data)
            if msg:
                return msg[:1200]
    except Exception:
        pass

    meta = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
    nested = data.get("result") if isinstance(data.get("result"), dict) else {}

    def _s(*vals: object) -> str:
        for v in vals:
            if isinstance(v, str) and v.strip():
                return v.strip()
        return ""

    if nested:
        err = _s(nested.get("error"), nested.get("stderr"), nested.get("verify_error"))
        skill = _s(nested.get("skill"))
        worker = _s(nested.get("worker"), nested.get("executor"))
        method = _s(nested.get("method"))
        summary = _s(nested.get("summary"), nested.get("stdout"), nested.get("output"))
        if err:
            parts = []
            if worker:
                parts.append(f"worker={worker}")
            if skill:
                parts.append(f"skill={skill}")
            stage = _s(nested.get("phase"), nested.get("stage"), meta.get("phase"))
            if stage:
                parts.append(f"этап={stage}")
            head = " · ".join(parts)
            body = err[:1000]
            hint = ""
            low = err.lower()
            if "timeout" in low or "timed_out" in low:
                hint = " Подсказка: увеличьте timeout воркера или проверьте Ollama."
            elif "verify" in low or "тест" in low or "pytest" in low:
                hint = " Подсказка: смотрите verify/тесты; задача не помечена DONE."
            elif "busy" in low or "project_busy" in low:
                hint = " Подсказка: проект занят — задача отложена, повторится сама."
            return (f"{head}: {body}" if head else body) + hint
        if skill and method == "skill":
            preview = summary[:400] if summary else "ok"
            return f"skill:{skill} — {preview}"
        if worker and summary:
            return f"{worker}: {summary[:800]}"
        if summary:
            return summary[:1200]
        if skill:
            return f"skill:{skill}"
        if worker:
            return f"worker={worker}"

    for key in ("result", "output", "summary", "reply", "response", "message_out"):
        v = data.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()[:2000]
    for key in ("result", "summary", "verify_note", "worker_output"):
        v = meta.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()[:2000]
    err = data.get("error") or meta.get("error")
    if isinstance(err, str) and err.strip():
        return err.strip()[:1200]
    status = data.get("status") or ""
    worker = data.get("worker") or meta.get("worker") or ""
    parts = [p for p in (str(status), str(worker)) if p]
    return " · ".join(parts) if parts else "готово"
