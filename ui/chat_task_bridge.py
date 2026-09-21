# -*- coding: utf-8 -*-
"""Day-6/14: pure Chat ↔ Task display bridge (no CustomTkinter).

Documents and tests the product path:

  task row (JSON)
       ↓
  format_progress_event / format_terminal_event
       ↓
  chat bubble text + phase footer

chat_panel may call these or keep result_text path; both share progress_ux / error_ux.
Day 14: ERROR path merges recovery_ux via chat_recovery_bridge when metadata present.
"""
from __future__ import annotations

from typing import Any


def _state(row: dict[str, Any]) -> str:
    return str(
        row.get("_state") or row.get("status") or ""
    ).strip().lower()


def format_progress_event(row: dict[str, Any] | None) -> dict[str, str]:
    """PENDING/PROCESSING/VERIFYING → chat line + phase_label text."""
    row = dict(row or {})
    st = _state(row)
    try:
        from core.progress_ux import progress_from_row, format_progress_line

        line = progress_from_row(row)
        if not line:
            meta = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
            phase = str(meta.get("phase") or row.get("phase") or st or "processing")
            worker = ""
            res = row.get("result") if isinstance(row.get("result"), dict) else {}
            worker = str(res.get("worker") or meta.get("worker") or "")
            line = format_progress_line(phase=phase, worker=worker)
    except Exception:
        line = f"▶ {st or '…'}"
    phase_footer = line
    try:
        from ui.chat_messages import format_phase_footer

        meta = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
        phase = str(meta.get("phase") or row.get("phase") or st)
        res = row.get("result") if isinstance(row.get("result"), dict) else {}
        worker = str(res.get("worker") or meta.get("worker") or "")
        phase_footer = format_phase_footer(phase, worker=worker)
    except Exception:
        pass
    # PC-GAP: show advisory route from metadata if present (not select_executor)
    try:
        meta = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
        rp = meta.get("route_preview") if isinstance(meta.get("route_preview"), dict) else {}
        worker = str(rp.get("worker") or "").strip()
        if worker and worker.lower() not in (line or "").lower():
            line = f"{line} · {worker}".strip(" ·")
            if phase_footer and worker not in phase_footer:
                phase_footer = f"{phase_footer} · {worker}"[:90]
    except Exception:
        pass
    return {"chat": line, "phase": phase_footer, "kind": "info"}


def format_terminal_event(row: dict[str, Any] | None) -> dict[str, str]:
    """DONE / ERROR → chat block (no extra DONE:/ERROR: prefix needed).

    ERROR rows: merge recovery bridge when replan/block/plan_outcome present.
    """
    row = dict(row or {})
    st = _state(row)
    try:
        from ui.chat_messages import format_terminal_for_chat

        body = format_terminal_for_chat(row)
    except Exception:
        try:
            from ui.result_text import extract_result_text

            body = extract_result_text(row)
        except Exception:
            body = "готово" if st == "done" else "ошибка"
    kind = "done" if st in ("done",) else "error"
    if st in ("error", "errors", "failed"):
        kind = "error"
    elif st == "done":
        kind = "done"

    out: dict[str, str] = {
        "chat": body,
        "phase": (body or "").split("\n")[0][:90],
        "kind": kind,
    }

    if kind == "error":
        try:
            from ui.chat_recovery_bridge import (
                format_error_row_for_chat,
                merge_terminal_with_recovery,
            )

            recovery = format_error_row_for_chat(row)
            out = merge_terminal_with_recovery(out, recovery)
        except Exception:
            pass
    return out


def format_task_event(row: dict[str, Any] | None) -> dict[str, str]:
    """Unified entry: any task row → display dict."""
    row = dict(row or {})
    st = _state(row)
    if st in ("done", "error", "errors", "failed", "cancelled", "canceled"):
        return format_terminal_event(row)
    if st in (
        "processing",
        "claimed",
        "running",
        "verifying",
        "pending",
        "queued",
        "deferred",
        "retry",
        "incoming",
    ):
        return format_progress_event(row)
    try:
        from ui.chat_messages import format_task_chat_block

        return {"chat": format_task_chat_block(row), "phase": st or "…", "kind": "info"}
    except Exception:
        return {"chat": st or "…", "phase": "…", "kind": "info"}


def should_prefix_role_label(body: str, kind: str) -> bool:
    """Avoid 'DONE: ✓ Готово' double marking and recovery marker double-prefix."""
    b = (body or "").lstrip()
    if kind == "done" and (b.startswith("✓") or b.startswith("Готово")):
        return False
    if kind == "error" and (
        b.startswith("⚠")
        or b.startswith("Не выполнено")
        or b.startswith("ERROR")
        or b.startswith("↻")
        or b.startswith("⏸")
    ):
        return False
    return True
