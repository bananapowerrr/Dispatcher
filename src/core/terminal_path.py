# -*- coding: utf-8 -*-
"""R1: unified terminal path for Runtime.

Single internal operation:
  finish_task → evidence → bus folder → queue terminal → emit → log

Does NOT change FSM semantics. Worker cannot declare DONE.
"""
from __future__ import annotations

from typing import Any, Callable


FOLDER = {
    "DONE": "done",
    "ERROR": "errors",
    "DEFERRED": "deferred",
}

STATUS_FROM_FOLDER = {
    "done": "DONE",
    "errors": "ERROR",
    "deferred": "DEFERRED",
}


def normalize_terminal_state(state: str) -> str:
    s = str(state or "").strip().upper()
    if s in ("DONE", "OK", "SUCCESS"):
        return "DONE"
    if s in ("ERROR", "FAIL", "FAILED", "ERRORS"):
        return "ERROR"
    if s in ("DEFERRED", "DEFER"):
        return "DEFERRED"
    return s


def verification_allows_done(result: dict[str, Any] | None) -> bool:
    """DONE only if result carries an explicit positive verification signal."""
    res = dict(result or {})
    if res.get("error") and not (
        res.get("verified")
        or res.get("verify_ok")
        or (isinstance(res.get("verification"), dict) and res["verification"].get("ok"))
    ):
        return False
    if res.get("verified") is True or res.get("verify_ok") is True:
        return True
    ver = res.get("verification")
    if isinstance(ver, dict) and ver.get("ok") is True:
        return True
    if res.get("verify") in (True, "PASS", "pass", "ok"):
        return True
    # Historical success path: worker name + git without explicit fail
    if res.get("worker") and not res.get("error") and res.get("tests_passed") is True:
        return True
    return False


def enforce_done_contract(
    terminal_state: str,
    result: dict[str, Any] | None,
) -> tuple[str, dict[str, Any]]:
    """If caller asks DONE without verification → demote to ERROR."""
    state = normalize_terminal_state(terminal_state)
    res = dict(result or {})
    if state == "DONE" and not verification_allows_done(res):
        res = dict(res)
        res.setdefault("error", res.get("error") or "done_without_verification")
        res["verified"] = False
        if not isinstance(res.get("verification"), dict):
            res["verification"] = {"ok": False, "reason": "done_without_verification"}
        else:
            res["verification"] = {**res["verification"], "ok": False}
        return "ERROR", res
    return state, res


def build_terminal_result(
    *,
    error: str = "",
    worker: str = "",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    out: dict[str, Any] = dict(extra or {})
    if worker and "worker" not in out:
        out["worker"] = worker
    if error and "error" not in out:
        out["error"] = str(error)[:2000]
    return out
