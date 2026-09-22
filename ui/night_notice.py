# -*- coding: utf-8 -*-
"""NIGHT-UI-001: Chat/Settings helpers for Night Mode status + morning report.

Does not start Runtime or enqueue tasks — status/report only.
"""
from __future__ import annotations

from typing import Any


def night_status_snapshot() -> dict[str, Any]:
    """Lightweight status for Settings / Chat."""
    out: dict[str, Any] = {
        "is_night": False,
        "max_parallel": 1,
        "active_run": None,
        "error": "",
    }
    try:
        from intelligence.night_scheduler import NightScheduler

        sched = NightScheduler()
        out["is_night"] = bool(sched.is_night())
        out["max_tasks"] = int(sched.config.max_tasks_per_night)
        out["min_complexity"] = int(sched.config.min_complexity)
    except Exception as exc:
        out["error"] = f"scheduler:{type(exc).__name__}"
    try:
        from core.night_run_state import find_resumable_run, default_state_dir

        run = find_resumable_run(default_state_dir())
        if run:
            out["active_run"] = {
                "run_id": run.get("run_id"),
                "status": run.get("status"),
                "phase": run.get("phase"),
                "current_step_id": run.get("current_step_id"),
                "completed_n": len(run.get("completed_steps") or []),
                "failed_n": len(run.get("failed_steps") or []),
            }
    except Exception:
        try:
            from intelligence.night_run_state import find_resumable_run, default_state_dir

            run = find_resumable_run(default_state_dir())
            if run:
                out["active_run"] = {
                    "run_id": run.get("run_id"),
                    "status": run.get("status"),
                    "phase": run.get("phase"),
                    "current_step_id": run.get("current_step_id"),
                    "completed_n": len(run.get("completed_steps") or []),
                    "failed_n": len(run.get("failed_steps") or []),
                }
        except Exception as exc:
            if not out.get("error"):
                out["error"] = f"run_state:{type(exc).__name__}"
    return out


def format_night_status_line(snap: dict[str, Any] | None = None) -> str:
    s = dict(snap or night_status_snapshot())
    window = "ночь" if s.get("is_night") else "день"
    line = f"Night Mode · окно: {window} · parallel=1"
    ar = s.get("active_run")
    if isinstance(ar, dict) and ar.get("run_id"):
        line += (
            f" · run {str(ar.get('run_id'))[:8]}…"
            f" [{ar.get('status')}/{ar.get('phase')}]"
            f" done={ar.get('completed_n')} fail={ar.get('failed_n')}"
        )
    else:
        line += " · активного run нет"
    if s.get("error"):
        line += f" · ({s['error']})"
    return line


def build_morning_report_text(
    *,
    session: dict[str, Any] | None = None,
    selection: dict[str, Any] | None = None,
    run_state: dict[str, Any] | None = None,
) -> str:
    try:
        from core.night_policy import build_morning_report

        return build_morning_report(
            session_result=session,
            selection=selection,
            run_state=run_state,
        )
    except Exception:
        try:
            from intelligence.night_policy import build_morning_report

            return build_morning_report(
                session_result=session,
                selection=selection,
                run_state=run_state,
            )
        except Exception as exc:
            return f"# Morning Report\n\n(недоступен: {type(exc).__name__}: {exc})\n"


def morning_report_from_last_run() -> str:
    """Load latest finished/resumable run and format morning report."""
    run = None
    try:
        from core.night_run_state import default_state_dir, find_resumable_run, load_state
        from pathlib import Path

        d = default_state_dir()
        run = find_resumable_run(d)
        if run is None and d.is_dir():
            # pick newest json
            files = sorted(d.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
            for f in files[:5]:
                st = load_state(f)
                if st:
                    run = st
                    break
    except Exception:
        try:
            from intelligence.night_run_state import default_state_dir, find_resumable_run, load_state

            d = default_state_dir()
            run = find_resumable_run(d)
        except Exception:
            run = None
    if not run:
        return "# Morning Report\n\nНет сохранённых night run.\n"
    session = {
        "stopped_reason": run.get("stop_reason") or run.get("status"),
        "done": list(run.get("completed_steps") or []),
        "errors": list(run.get("failed_steps") or []),
        "deferred": list(run.get("deferred_steps") or []),
        "replans": [],
        "summary": f"run_id={run.get('run_id')} phase={run.get('phase')}",
    }
    return build_morning_report_text(session=session, run_state=run)
