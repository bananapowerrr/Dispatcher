# -*- coding: utf-8 -*-
"""DEV-004 Worker Fallback v1.

Fallback to another worker is allowed only for infrastructure failures:

  timeout | unavailable | missing executable | network | rate_limit | billing

NOT allowed for:
  verification_failed | invalid_output (when same attempt) | security | auth
  (auth → ask_user via recovery; not silent switch forever)

Does not enqueue tasks. Does not declare DONE.
"""
from __future__ import annotations

from typing import Any

# fallback_kind / WorkerResult.status / outcome kind → allow switch
ALLOW_FALLBACK_KINDS = frozenset({
    "timeout",
    "network",
    "rate_limit",
    "billing",
    "other",  # used for unavailable/crash in KIND_TO_FALLBACK — refined below
})

ALLOW_FALLBACK_STATUS = frozenset({
    "timeout",
    "unavailable",
    "failure",  # only if not auth-only — refined by kind
})

ALLOW_FALLBACK_OUTCOME_KIND = frozenset({
    "worker_timeout",
    "worker_unavailable",
    "worker_network",
    "worker_rate_limit",
    "worker_billing",
    "worker_crash",  # missing binary often surfaces as crash
})

DENY_FALLBACK_OUTCOME_KIND = frozenset({
    "verification_failed",
    "worker_loop",
    "worker_model",
    "worker_auth",
    "worker_ok",
    "security_violation",
})


def allow_worker_fallback(
    *,
    kind: str = "",
    status: str = "",
    fallback_kind: str = "",
    worker_result: dict[str, Any] | None = None,
    recovery_decision: dict[str, Any] | None = None,
) -> bool:
    """True if Runtime may try another worker in the same task loop."""
    wr = dict(worker_result or {})
    rd = dict(recovery_decision or {})
    if "allow_fallback" in rd:
        return bool(rd.get("allow_fallback"))

    k = str(kind or wr.get("kind") or "")
    st = str(status or wr.get("status") or "")
    fb = str(fallback_kind or wr.get("fallback_kind") or "")

    if k in DENY_FALLBACK_OUTCOME_KIND:
        return False
    if st == "invalid_output":
        return False
    if st == "success":
        return False
    if k in ALLOW_FALLBACK_OUTCOME_KIND:
        return True
    if st in ("timeout", "unavailable"):
        return True
    if fb in ("timeout", "network", "rate_limit", "billing"):
        return True
    # generic failure: allow only once infrastructure-ish
    if st == "failure" and k in ("worker_crash", "worker_network", ""):
        return True
    return False


def filter_fallback_pool(
    workers: list[Any],
    *,
    tried: list[str] | None = None,
    kind: str = "",
    status: str = "",
    fallback_kind: str = "",
    worker_result: dict[str, Any] | None = None,
    offline: bool | None = None,
) -> list[Any]:
    """Return alternate workers if fallback allowed; else empty list."""
    if not allow_worker_fallback(
        kind=kind,
        status=status,
        fallback_kind=fallback_kind,
        worker_result=worker_result,
    ):
        return []
    try:
        from core.fallback import order_candidates

        return order_candidates(
            workers,
            tried=tried,
            failure_kind=fallback_kind or kind or None,
            offline=offline,
        )
    except Exception:
        tried_set = set(tried or [])
        return [w for w in workers if getattr(w, "name", None) not in tried_set]


def annotate_fallback_decision(
    meta: dict[str, Any] | None,
    *,
    allowed: bool,
    reason: str = "",
    from_worker: str = "",
    to_worker: str = "",
) -> dict[str, Any]:
    m = dict(meta or {})
    m["worker_fallback"] = {
        "allowed": bool(allowed),
        "reason": str(reason or ""),
        "from": str(from_worker or ""),
        "to": str(to_worker or ""),
    }
    return m
