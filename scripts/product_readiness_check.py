#!/usr/bin/env python3
"""Offline product readiness — import + contract smoke (no Ollama)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

CHECKS: list[tuple[str, bool, str]] = []


def ok(name: str, passed: bool, detail: str = "") -> None:
    CHECKS.append((name, passed, detail))
    mark = "OK" if passed else "FAIL"
    print(f"  [{mark}] {name}" + (f" — {detail}" if detail else ""))


def main() -> int:
    print("AgentBus product readiness (offline)\n")

    # Core modules
    for mod in (
        "core.runtime_decision",
        "core.recovery_policy",
        "core.worker_failure_contract",
        "core.worker_fallback",
        "core.task_continuity",
        "core.night_mode_controller",
        "core.night_run_state",
        "core.night_policy",
        "core.night_runtime_bridge",
        "core.context_audit_attach",
        "intelligence.context_budget",
    ):
        try:
            __import__(mod)
            ok(f"import {mod}", True)
        except Exception as exc:
            ok(f"import {mod}", False, f"{type(exc).__name__}: {exc}")

    # Contracts
    try:
        from core.runtime_decision import decide_terminal, evidence_snapshot
        d = decide_terminal(evidence_snapshot(exec_ok=True))
        ok("DONE requires verify", d["terminal_state"] != "DONE")
        snap = evidence_snapshot(exec_ok=True, verification={"ok": True, "passed": True})
        # do not pre-set terminal_state — decide_terminal owns it
        d2 = decide_terminal(snap)
        ok("DONE with verify", d2["terminal_state"] == "DONE", d2.get("reason") or "")
    except Exception as e:
        ok("runtime_decision", False, str(e))

    try:
        from core.worker_fallback import allow_worker_fallback
        ok("fallback deny verify", allow_worker_fallback(kind="verification_failed") is False)
        ok("fallback allow timeout", allow_worker_fallback(kind="worker_timeout") is True)
    except Exception as e:
        ok("worker_fallback", False, str(e))

    try:
        from core.night_runtime_bridge import make_execute_fn
        fn = make_execute_fn(mock=True)
        out = fn({"metadata": {"plan_step_id": "s0"}})
        ok("night mock DONE", out.get("terminal_state") == "DONE" and out.get("verified") is True)
    except Exception as e:
        ok("night_runtime_bridge", False, str(e))

    try:
        from core.task_continuity import continuity_for_next_prompt
        b = continuity_for_next_prompt({
            "attempts": 1,
            "result": {"error": "x", "verification": {"ok": False}, "changed_files": ["a.py"]},
        })
        ok("continuity block", "PREVIOUS ATTEMPT" in b)
    except Exception as e:
        ok("task_continuity", False, str(e))

    # UI modules (optional if no tk)
    for mod in ("ui.night_notice", "ui.chat_recovery_bridge", "ui.update_notice"):
        try:
            __import__(mod)
            ok(f"import {mod}", True)
        except Exception as exc:
            ok(f"import {mod}", False, f"{type(exc).__name__}: {exc}")

    failed = sum(1 for _, p, _ in CHECKS if not p)
    print(f"\n{len(CHECKS) - failed}/{len(CHECKS)} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
