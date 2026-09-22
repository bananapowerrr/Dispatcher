# -*- coding: utf-8 -*-
"""DEV-006 Task context / conversation continuity.

Builds a structured "previous attempt" block for the next worker prompt:

  previous attempt N
  → failure evidence
  → changed files / diff summary
  → verification result
  → instruction: fix Y, do not undo X

Does not enqueue or change FSM.
"""
from __future__ import annotations

from typing import Any

MAX_BLOCK_CHARS = 2_500
MAX_DIFF_CHARS = 800
MAX_ERROR_CHARS = 600


def _ver_summary(verification: dict[str, Any] | None) -> str:
    v = dict(verification or {})
    if not v:
        return ""
    if v.get("ok") is True or v.get("passed") is True:
        return "verification: PASS"
    reason = str(v.get("reason") or v.get("summary") or v.get("result") or "FAIL")
    return f"verification: FAIL — {reason[:300]}"


def build_previous_attempt_block(
    *,
    attempt: int = 0,
    error: str = "",
    verification: dict[str, Any] | None = None,
    changed_files: list[str] | None = None,
    diff_summary: str = "",
    worker: str = "",
    failure_kind: str = "",
    stdout_summary: str = "",
    stderr_summary: str = "",
) -> str:
    """Human-readable block for the next worker message."""
    lines: list[str] = []
    n = max(1, int(attempt or 1))
    lines.append(f"PREVIOUS ATTEMPT #{n}")
    if worker:
        lines.append(f"worker: {worker}")
    if failure_kind:
        lines.append(f"failure_kind: {failure_kind}")
    err = str(error or "").strip()
    if err:
        lines.append("error:")
        lines.append(err[:MAX_ERROR_CHARS])
    ver = _ver_summary(verification)
    if ver:
        lines.append(ver)
    files = [str(x) for x in (changed_files or []) if str(x).strip()]
    if files:
        lines.append("changed_files (keep unless wrong):")
        for f in files[:20]:
            lines.append(f"  - {f}")
    diff = str(diff_summary or "").strip()
    if diff:
        lines.append("diff_summary:")
        lines.append(diff[:MAX_DIFF_CHARS])
    se = str(stderr_summary or "").strip()
    if se and se not in err:
        lines.append("stderr:")
        lines.append(se[:400])
    lines.append(
        "INSTRUCTION: Fix the verification/error above. "
        "Do not revert unrelated changes from changed_files."
    )
    text = "\n".join(lines)
    if len(text) > MAX_BLOCK_CHARS:
        text = text[: MAX_BLOCK_CHARS - 20] + "\n…[truncated]"
    return text


def extract_attempt_context(payload: dict[str, Any] | None) -> dict[str, Any]:
    """Pull continuity fields from task row / ERROR result."""
    raw = dict(payload or {})
    meta = raw.get("metadata") if isinstance(raw.get("metadata"), dict) else {}
    res = raw.get("result") if isinstance(raw.get("result"), dict) else {}
    ev = meta.get("execution_evidence") if isinstance(meta.get("execution_evidence"), dict) else {}
    wr = meta.get("worker_result") if isinstance(meta.get("worker_result"), dict) else {}
    attempt = int(
        raw.get("attempts")
        or meta.get("attempts")
        or ev.get("attempt")
        or 0
    )
    changed = list(
        res.get("changed_files")
        or meta.get("changed_files")
        or ev.get("changed_files")
        or []
    )
    verification = (
        res.get("verification")
        if isinstance(res.get("verification"), dict)
        else (ev.get("verification") if isinstance(ev.get("verification"), dict) else {})
    )
    return {
        "attempt": attempt,
        "error": str(res.get("error") or raw.get("error") or ev.get("error") or wr.get("error") or ""),
        "verification": verification,
        "changed_files": changed,
        "diff_summary": str(res.get("diff_summary") or meta.get("diff_summary") or res.get("diff") or "")[:MAX_DIFF_CHARS],
        "worker": str(res.get("worker") or wr.get("worker") or meta.get("worker") or ""),
        "failure_kind": str(
            meta.get("failure_kind")
            or wr.get("kind")
            or meta.get("failure_layer")
            or ""
        ),
        "stdout_summary": str(res.get("stdout") or ev.get("stdout_summary") or "")[-500:],
        "stderr_summary": str(res.get("stderr") or ev.get("stderr_summary") or wr.get("stderr_summary") or "")[-500:],
    }


def continuity_for_next_prompt(payload: dict[str, Any] | None) -> str:
    """One-shot: task payload → previous attempt block (or empty)."""
    ctx = extract_attempt_context(payload)
    if not ctx.get("error") and not ctx.get("verification") and not ctx.get("changed_files"):
        # nothing to continue
        if int(ctx.get("attempt") or 0) <= 0:
            return ""
    return build_previous_attempt_block(**ctx)


def merge_prev_failure(
    existing: str,
    payload: dict[str, Any] | None,
) -> str:
    """Prefer structured continuity over raw error string."""
    block = continuity_for_next_prompt(payload)
    if block:
        return block
    return str(existing or "")[:800]
