# -*- coding: utf-8 -*-
"""DEV-008 Persistent Night Run / Crash Recovery.

Atomic state file, single-run lock, resume without blind re-CLAIM / false DONE.
"""
from __future__ import annotations

import json
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MAX_ACTIVE_NIGHT_RUNS = 1

# Terminal / phase values
STATUS_RUNNING = "RUNNING"
STATUS_COMPLETED = "COMPLETED"
STATUS_STOPPED = "STOPPED"
STATUS_ASK_USER = "ASK_USER"
STATUS_CRASHED = "CRASHED"

PHASE_IDLE = "idle"
PHASE_STEP_STARTED = "step_started"
PHASE_EXECUTION_FINISHED = "execution_finished"
PHASE_VERIFICATION_FINISHED = "verification_finished"
PHASE_RECOVERY_FINISHED = "recovery_finished"
PHASE_TERMINAL = "terminal"

# Interrupted mid-flight — never auto-DONE
UNSAFE_PHASES = frozenset({
    PHASE_STEP_STARTED,
    PHASE_EXECUTION_FINISHED,
    PHASE_VERIFICATION_FINISHED,
})

SECRET_KEYS = frozenset({
    "api_key", "token", "password", "secret", "authorization",
    "openai_api_key", "anthropic_api_key", "credentials",
})


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def default_state_dir() -> Path:
    env = os.getenv("AGENTBUS_NIGHT_STATE_DIR")
    if env:
        return Path(env)
    base = os.getenv("AGENTBUS_USER_DATA")
    if base:
        return Path(base) / "night_runs"
    return Path.home() / "AppData" / "Roaming" / "AgentBus" / "night_runs"


def state_path_for(run_id: str, state_dir: Path | None = None) -> Path:
    d = state_dir or default_state_dir()
    return d / f"{run_id}.json"


def lock_path(state_dir: Path | None = None) -> Path:
    d = state_dir or default_state_dir()
    return d / "night_run.lock"


def strip_secrets(obj: Any) -> Any:
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if str(k).lower() in SECRET_KEYS or "secret" in str(k).lower() or "api_key" in str(k).lower():
                continue
            if k in ("stdout", "stderr", "stdout_summary", "stderr_summary"):
                # keep short only
                s = str(v or "")
                out[k] = s[:200] if s else ""
                continue
            out[k] = strip_secrets(v)
        return out
    if isinstance(obj, list):
        return [strip_secrets(x) for x in obj[:50]]
    return obj


def new_run_state(
    *,
    project_id: str = "",
    plan_step_ids: list[str] | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    rid = run_id or str(uuid.uuid4())
    now = _utc_now()
    return {
        "run_id": rid,
        "status": STATUS_RUNNING,
        "phase": PHASE_IDLE,
        "started_at": now,
        "updated_at": now,
        "project_id": str(project_id or ""),
        "current_step_id": "",
        "current_attempt": 0,
        "completed_steps": [],
        "failed_steps": [],
        "deferred_steps": [],
        "attempts": {},
        "recovery_actions": [],
        "stop_reason": "",
        "plan_step_ids": list(plan_step_ids or []),
        "last_terminal": "",
        "interrupted": False,
    }


def atomic_write_state(path: Path, state: dict[str, Any]) -> None:
    """tmp → fsync → replace. Never writes secrets."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    clean = strip_secrets(dict(state))
    clean["updated_at"] = _utc_now()
    data = json.dumps(clean, ensure_ascii=False, indent=2, sort_keys=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def load_state(path: Path) -> dict[str, Any] | None:
    path = Path(path)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or not data.get("run_id"):
            return None
        return data
    except Exception:
        return None


def checkpoint(
    path: Path,
    state: dict[str, Any],
    *,
    phase: str,
    step_id: str = "",
    terminal: str = "",
    attempt: int | None = None,
    recovery_action: str = "",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    st = dict(state)
    st["phase"] = phase
    if step_id:
        st["current_step_id"] = step_id
    if terminal:
        st["last_terminal"] = terminal
    if attempt is not None:
        st["current_attempt"] = int(attempt)
        attempts = dict(st.get("attempts") or {})
        key = f"{step_id}:{attempt}"
        attempts[key] = {"phase": phase, "terminal": terminal, "at": _utc_now()}
        st["attempts"] = attempts
    if recovery_action:
        actions = list(st.get("recovery_actions") or [])
        op_id = f"{st.get('run_id')}:{step_id}:{recovery_action}:{st.get('current_attempt')}"
        if op_id not in {a.get("op_id") for a in actions if isinstance(a, dict)}:
            actions.append({
                "op_id": op_id,
                "action": recovery_action,
                "step_id": step_id,
                "at": _utc_now(),
            })
            st["recovery_actions"] = actions
    if phase == PHASE_TERMINAL and terminal == "DONE" and step_id:
        done = list(st.get("completed_steps") or [])
        if step_id not in done:
            done.append(step_id)
        st["completed_steps"] = done
    if phase == PHASE_TERMINAL and terminal == "ERROR" and step_id:
        failed = list(st.get("failed_steps") or [])
        if step_id not in failed:
            failed.append(step_id)
        st["failed_steps"] = failed
    if phase == PHASE_TERMINAL and terminal == "DEFERRED" and step_id:
        deferred = list(st.get("deferred_steps") or [])
        if step_id not in deferred:
            deferred.append(step_id)
        st["deferred_steps"] = deferred
    if extra:
        for k, v in extra.items():
            if k not in SECRET_KEYS:
                st[k] = v
    atomic_write_state(path, st)
    return st


def acquire_lock(state_dir: Path | None = None, *, run_id: str = "") -> dict[str, Any]:
    """Single active night run. Returns {ok, error?, lock_path}."""
    lp = lock_path(state_dir)
    lp.parent.mkdir(parents=True, exist_ok=True)
    if lp.is_file():
        try:
            existing = json.loads(lp.read_text(encoding="utf-8"))
            # stale lock > 24h → allow steal
            age = time.time() - float(existing.get("mtime") or 0)
            if age < 86400 and existing.get("run_id") and existing.get("run_id") != run_id:
                return {
                    "ok": False,
                    "error": "night_run_already_active",
                    "active_run_id": existing.get("run_id"),
                    "lock_path": str(lp),
                }
        except Exception:
            pass
    payload = {
        "run_id": run_id,
        "mtime": time.time(),
        "pid": os.getpid(),
        "at": _utc_now(),
    }
    tmp = lp.with_suffix(".lock.tmp")
    tmp.write_text(json.dumps(payload), encoding="utf-8")
    os.replace(tmp, lp)
    return {"ok": True, "lock_path": str(lp), "run_id": run_id}


def release_lock(state_dir: Path | None = None, *, run_id: str = "") -> None:
    lp = lock_path(state_dir)
    if not lp.is_file():
        return
    try:
        existing = json.loads(lp.read_text(encoding="utf-8"))
        if run_id and existing.get("run_id") and existing.get("run_id") != run_id:
            return
    except Exception:
        pass
    try:
        lp.unlink()
    except Exception:
        pass


def find_resumable_run(state_dir: Path | None = None) -> dict[str, Any] | None:
    d = state_dir or default_state_dir()
    if not d.is_dir():
        return None
    candidates: list[dict[str, Any]] = []
    for p in sorted(d.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
        if p.name.endswith(".tmp"):
            continue
        st = load_state(p)
        if not st:
            continue
        if st.get("status") == STATUS_RUNNING:
            candidates.append(st)
            break
    return candidates[0] if candidates else None


def resume_plan(
    state: dict[str, Any],
) -> dict[str, Any]:
    """Decide how to resume after restart. Never auto-DONE interrupted work."""
    st = dict(state or {})
    phase = str(st.get("phase") or PHASE_IDLE)
    step_id = str(st.get("current_step_id") or "")
    completed = set(st.get("completed_steps") or [])
    failed = set(st.get("failed_steps") or [])

    if st.get("status") in (STATUS_COMPLETED, STATUS_STOPPED, STATUS_ASK_USER):
        return {
            "action": "none",
            "reason": "run_already_finished",
            "skip_steps": list(completed | failed),
        }

    if phase in UNSAFE_PHASES and step_id:
        # Interrupted mid-step — mark interrupted, do not claim DONE
        return {
            "action": "recover_interrupted",
            "reason": f"interrupted_in_{phase}",
            "step_id": step_id,
            "skip_steps": list(completed),
            "do_not_auto_done": True,
            "suggested_terminal": "ERROR",
        }

    return {
        "action": "continue",
        "reason": "safe_resume",
        "skip_steps": list(completed | failed | set(st.get("deferred_steps") or [])),
        "do_not_auto_done": False,
    }


def mark_run_finished(path: Path, state: dict[str, Any], *, status: str, stop_reason: str) -> dict[str, Any]:
    st = dict(state)
    st["status"] = status
    st["stop_reason"] = stop_reason
    st["phase"] = PHASE_TERMINAL
    st["current_step_id"] = ""
    atomic_write_state(path, st)
    return st


def is_step_done(state: dict[str, Any], step_id: str) -> bool:
    return str(step_id) in set(state.get("completed_steps") or [])


def recovery_already_applied(state: dict[str, Any], step_id: str, action: str, attempt: int) -> bool:
    op_id = f"{state.get('run_id')}:{step_id}:{action}:{attempt}"
    for a in state.get("recovery_actions") or []:
        if isinstance(a, dict) and a.get("op_id") == op_id:
            return True
    return False
