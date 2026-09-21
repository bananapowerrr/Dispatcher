# -*- coding: utf-8 -*-
"""Task execution evidence record (Runtime contract helper).

Builds a structured snapshot for DONE/ERROR without granting workers
the right to declare DONE. Terminal state is always caller-supplied.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


REQUIRED_KEYS = (
    "task_id",
    "worker",
    "attempt",
    "terminal_state",
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_execution_evidence(
    *,
    task_id: str = "",
    worker: str = "",
    model: str = "",
    attempt: int = 0,
    plan_step: str = "",
    started_at: str = "",
    finished_at: str = "",
    changed_files: list[str] | None = None,
    verification: dict[str, Any] | None = None,
    terminal_state: str = "",
    error: str = "",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a serializable execution evidence dict.

    Contract:
    - terminal_state is set only by Runtime (caller), never inferred from worker OK.
    - verification dict is optional but should reflect gate outcome when present.
    """
    term = str(terminal_state or "").strip().upper()
    if term in ("DONE", "ERROR", "DEFERRED", "DEDUPED", ""):
        pass
    else:
        # normalize common variants
        if term in ("OK", "SUCCESS"):
            term = "DONE"
        elif term in ("FAIL", "FAILED", "ERRORS"):
            term = "ERROR"

    ev: dict[str, Any] = {
        "task_id": str(task_id or ""),
        "plan_step": str(plan_step or ""),
        "worker": str(worker or ""),
        "model": str(model or ""),
        "attempt": int(attempt or 0),
        "started_at": str(started_at or ""),
        "finished_at": str(finished_at or "") or _utc_now(),
        "changed_files": [str(x) for x in (changed_files or [])][:50],
        "verification": dict(verification or {}),
        "terminal_state": term,
    }
    if error:
        ev["error"] = str(error)[:2000]
    if extra:
        for k, v in extra.items():
            if k not in ev:
                ev[k] = v
    return ev


def evidence_from_task_payload(
    payload: dict[str, Any] | None,
    *,
    terminal_state: str = "",
    state_folder: str = "",
) -> dict[str, Any]:
    """Derive evidence from a task JSON payload + explicit terminal state."""
    raw = dict(payload or {})
    meta = raw.get("metadata") if isinstance(raw.get("metadata"), dict) else {}
    res = raw.get("result") if isinstance(raw.get("result"), dict) else {}
    rp = meta.get("route_preview") if isinstance(meta.get("route_preview"), dict) else {}

    term = terminal_state
    if not term and state_folder:
        term = {"done": "DONE", "errors": "ERROR", "deferred": "DEFERRED"}.get(
            state_folder, ""
        )
    if not term:
        term = str(raw.get("status") or "").upper()

    worker = str(
        res.get("worker")
        or raw.get("worker")
        or raw.get("executor")
        or rp.get("worker")
        or meta.get("worker")
        or ""
    )
    model = str(res.get("model") or meta.get("model") or rp.get("model") or "")
    attempt = int(raw.get("attempts") or meta.get("attempts") or 0)
    changed = res.get("changed_files") or meta.get("changed_files") or []
    if isinstance(changed, str):
        changed = [changed]
    ver = res.get("verification") if isinstance(res.get("verification"), dict) else {}
    if not ver and res.get("verify") is not None:
        ver = {"result": res.get("verify")}
    err = str(res.get("error") or raw.get("error") or "")
    started = str(meta.get("started_at") or raw.get("started_at") or "")
    plan_step = str(meta.get("plan_step") or meta.get("step_id") or "")

    return build_execution_evidence(
        task_id=str(raw.get("id") or ""),
        worker=worker,
        model=model,
        attempt=attempt,
        plan_step=plan_step,
        started_at=started,
        changed_files=list(changed),
        verification=ver,
        terminal_state=term,
        error=err,
        extra={
            "reclaim_reason": meta.get("reclaim_reason"),
            "route_advisory": bool(rp.get("advisory")) if rp else None,
        },
    )


def merge_evidence_into_payload(
    payload: dict[str, Any],
    evidence: dict[str, Any],
) -> dict[str, Any]:
    """Attach evidence under metadata.execution_evidence (non-destructive)."""
    out = dict(payload)
    meta = dict(out.get("metadata") if isinstance(out.get("metadata"), dict) else {})
    meta["execution_evidence"] = dict(evidence)
    out["metadata"] = meta
    # mirror terminal for quick grep without trusting worker
    if evidence.get("terminal_state"):
        out.setdefault("status", evidence["terminal_state"])
    return out


def worker_cannot_force_done(evidence: dict[str, Any], *, verified: bool) -> bool:
    """Contract helper: DONE only valid when verification passed."""
    term = str(evidence.get("terminal_state") or "").upper()
    if term != "DONE":
        return True
    return bool(verified)



def classify_failure_layer(
    *,
    error: str = "",
    reclaim_reason: str = "",
    verification: dict | None = None,
) -> tuple[str, bool]:
    """Return (failure_layer, recoverable).

    Layers are coarse product labels for Recovery / LIVE diagnosis.
    Does not change FSM — advisory metadata only.
    """
    rr = str(reclaim_reason or "").lower()
    if "max_attempts" in rr:
        return "reclaim_max_attempts", False
    if "heartbeat" in rr or "stuck" in rr:
        return "reclaim_no_heartbeat", True
    ver = dict(verification or {})
    if ver.get("ok") is False or str(ver.get("result") or "").lower() in ("fail", "failed"):
        return "verification", True
    err = str(error or "").lower()
    if any(x in err for x in ("ollama", "connection refused", "timeout", "timed out")):
        return "worker_infra", True
    if any(x in err for x in ("verify", "syntax", "static_guard", "pytest")):
        return "verification", True
    if any(x in err for x in ("aider", "llm", "model", "token")):
        return "worker_exec", True
    if err:
        return "unknown", True
    return "none", True
