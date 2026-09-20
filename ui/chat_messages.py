# -*- coding: utf-8 -*-
"""Day-4: chat bubble lines from task rows (no CustomTkinter deps).

Unifies progress_ux + error_ux + result_text for the product chat transcript.
Chat panel can call format_task_chat_block(row) instead of ad-hoc string logic.
"""
from __future__ import annotations

from typing import Any


def _nested(row: dict[str, Any]) -> dict[str, Any]:
    r = row.get("result") if isinstance(row.get("result"), dict) else {}
    return r if isinstance(r, dict) else {}


def _meta(row: dict[str, Any]) -> dict[str, Any]:
    m = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
    return m if isinstance(m, dict) else {}


def _status(row: dict[str, Any]) -> str:
    return str(
        row.get("_state")
        or row.get("status")
        or _nested(row).get("status")
        or ""
    ).strip().lower()


def _phase(row: dict[str, Any]) -> str:
    return str(
        _meta(row).get("phase")
        or _nested(row).get("phase")
        or _nested(row).get("stage")
        or ""
    ).strip()


def _worker(row: dict[str, Any]) -> str:
    return str(
        _nested(row).get("worker")
        or _meta(row).get("worker")
        or row.get("worker")
        or ""
    ).strip()


def _files_from_row(row: dict[str, Any]) -> list[str]:
    nested = _nested(row)
    meta = _meta(row)
    files: list[str] = []
    for key in ("files", "changed_files", "committed_files"):
        for src in (nested, meta, row):
            val = src.get(key) if isinstance(src, dict) else None
            if isinstance(val, list):
                files.extend(str(x) for x in val if x)
    # changes dict
    ch = nested.get("changes") if isinstance(nested.get("changes"), dict) else {}
    if isinstance(ch.get("files"), list):
        files.extend(str(x) for x in ch["files"] if x)
    # dedupe preserve order
    seen: set[str] = set()
    out: list[str] = []
    for f in files:
        if f not in seen:
            seen.add(f)
            out.append(f)
    return out[:20]


def format_progress_for_chat(row: dict[str, Any] | None) -> str:
    """Single progress line while task is non-terminal."""
    row = dict(row or {})
    try:
        from core.progress_ux import format_progress_line, progress_from_row

        line = progress_from_row(row)
        if line:
            return line
        return format_progress_line(
            phase=_phase(row) or _status(row),
            worker=_worker(row),
        )
    except Exception:
        st = _status(row) or _phase(row) or "…"
        w = _worker(row)
        return f"▶ {st}" + (f" · worker={w}" if w else "")


def format_terminal_for_chat(row: dict[str, Any] | None) -> str:
    """DONE / ERROR block for chat after task finishes."""
    row = dict(row or {})
    st = _status(row)
    nested = _nested(row)
    ok = st in ("done",) or (
        nested.get("ok") is True and st not in ("error", "failed", "errors")
    )
    failed = st in ("error", "errors", "failed") or nested.get("ok") is False

    files = _files_from_row(row)
    worker = _worker(row)

    if failed:
        try:
            from core.error_ux import humanize_from_row, retry_status_from_row
            from core.progress_ux import format_fail_summary

            human = humanize_from_row(row)
            retry = retry_status_from_row(row)
            hint = ""
            if "→" in human:
                hint = human.split("→", 1)[-1].strip()
            body = format_fail_summary(
                reason=human.split("\n")[0][:400] if human else "ошибка",
                human_hint=hint,
                can_retry=True,
            )
            if retry:
                body = body + "\n" + retry
            return body[:1500]
        except Exception:
            try:
                from ui.result_text import extract_result_text

                return "⚠ " + extract_result_text(row)[:1100]
            except Exception:
                return "⚠ Задача завершилась с ошибкой."

    if ok or st in ("done",):
        try:
            from core.progress_ux import format_done_summary

            tests_ok = None
            tests_detail = ""
            ver = nested.get("verification") or _meta(row).get("verification") or {}
            if isinstance(ver, dict):
                if ver.get("ok") is True or str(ver.get("status", "")).upper() == "PASS":
                    tests_ok = True
                    tests_detail = str(ver.get("summary") or ver.get("detail") or "")[:80]
                elif ver.get("ok") is False:
                    tests_ok = False
                    tests_detail = str(ver.get("summary") or "")[:80]
            return format_done_summary(
                files=files or None,
                tests_ok=tests_ok,
                tests_detail=tests_detail,
                worker=worker,
            )
        except Exception:
            try:
                from ui.result_text import extract_result_text

                return "✓ " + extract_result_text(row)[:1100]
            except Exception:
                return "✓ Готово"

    # non-terminal
    return format_progress_for_chat(row)


def format_task_chat_block(row: dict[str, Any] | None) -> str:
    """Public API for chat panel: one block per task event."""
    row = dict(row or {})
    st = _status(row)
    if st in ("done", "error", "errors", "failed", "cancelled", "canceled"):
        return format_terminal_for_chat(row)
    if st in (
        "processing",
        "claimed",
        "running",
        "verifying",
        "pending",
        "queued",
        "deferred",
        "retry",
    ):
        return format_progress_for_chat(row)
    # fallback
    try:
        from ui.result_text import extract_result_text

        return extract_result_text(row)
    except Exception:
        return format_progress_for_chat(row)


def format_phase_footer(phase: str | None, worker: str = "") -> str:
    """Short footer under chat input."""
    try:
        from ui.status_labels import phase_label

        label = phase_label(phase)
    except Exception:
        label = phase or "Ready"
    if worker:
        return f"{label} · {worker}"
    return str(label)
