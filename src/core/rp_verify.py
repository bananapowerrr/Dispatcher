# -*- coding: utf-8 -*-
"""Verify ladder, commit, quarantine.

Mixin for RuntimeProcess. Do not instantiate alone — used via Runtime MRO.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

try:
    from core.feature_flags import is_enabled
except Exception:  # pragma: no cover
    def is_enabled(name: str, default: bool = True) -> bool:
        return default

try:
    from core.config import VERIFY_FAIL_MAX
except Exception:  # pragma: no cover
    VERIFY_FAIL_MAX = 3


class RPVerifyMixin:
    def _phase_verify_and_commit(
        self,
        *,
        result,
        task,
        ctx,
        tests,
        worker,
        gitops,
        before_snapshot,
        plan,
        message: str,
        attempt_messages: dict,
    ) -> tuple[str, dict, str]:
        """VERIFY ladder + diff budget + git commit. Mutates result.ok/stderr."""
        commit_sha = ""

        try:
            self._set_phase(task, "verify")
            self._touch_task_lease(task, phase="verify")
        except Exception as exp:
            try:
                self.log.write(f"verify phase marker failed: {type(exp).__name__}: {exp}")
            except Exception:
                pass

        if not getattr(result, "ok", False):
            return message, attempt_messages, commit_sha

        try:
            self._emit(
                "TEST_START",
                "verify",
                task_id=getattr(task, "id", ""),
                worker=getattr(worker, "name", ""),
            )
            try:
                from utils.pipeline_events import verify_started
                verify_started(
                    str(getattr(task, "id", "")),
                    str(getattr(worker, "name", "")),
                )
            except Exception:
                pass
        except Exception:
            pass

        # Verification itself is a terminal safety gate. If the verifier
        # cannot run, do not let the successful worker result fall through
        # to commit/DONE.
        try:
            ok, verify_error = self._verify_escalating(
                task, ctx, tests, worker_name=getattr(worker, "name", "")
            )
        except Exception as exp:
            ok = False
            verify_error = (
                f"verification_exception: {type(exp).__name__}: {exp}"
            )
            try:
                self.log.write(verify_error)
            except Exception:
                pass

        # DONE Gate: verification-engine failures are fail-closed.
        if ok:
            try:
                gate_ok, gate_err = self._verification_engine_gate(
                    task, ctx, execution_ok=True
                )
                if not gate_ok:
                    ok, verify_error = (
                        False,
                        gate_err or "verification_gate_failed",
                    )
            except Exception as exp:
                ok = False
                verify_error = (
                    f"verification_gate_exception: "
                    f"{type(exp).__name__}: {exp}"
                )
                try:
                    self.log.write(verify_error)
                except Exception:
                    pass

        if not ok:
            result.stderr, result.ok = verify_error, False
            try:
                self._bump_verify_fails(task, verify_error or "")
            except Exception as exp:
                try:
                    self.log.write(
                        f"_bump_verify_fails: {type(exp).__name__}: {exp}"
                    )
                except Exception:
                    pass
            try:
                from utils.metrics import GLOBAL_METRICS
                meta_v = (
                    task.metadata
                    if isinstance(getattr(task, "metadata", None), dict)
                    else {}
                )
                lvl = int(
                    meta_v.get("verify_ladder")
                    or meta_v.get("verify_max_level")
                    or 0
                )
                GLOBAL_METRICS.record_verify_ladder(
                    success=False,
                    level=lvl,
                )
            except Exception:
                pass
            try:
                from intelligence.pev_loop import verify_retry_message
                message = verify_retry_message(
                    message,
                    verify_error or "",
                    int(task.attempts or 1),
                )
                attempt_messages = {}
            except Exception:
                pass
            return message, attempt_messages, commit_sha

        if plan is not None and not getattr(plan, "commitable", True):
            result.ok = False
            result.stderr = "Небезопасный git: " + plan.describe()
            return message, attempt_messages, commit_sha

        if plan is not None and getattr(plan, "stage", None):
            try:
                from core.task_safety import check_diff_budget

                budget = check_diff_budget(
                    root=str(ctx.root),
                    stage_paths=list(plan.stage or []),
                    task=task,
                )
                if not budget.get("ok", True):
                    result.ok = False
                    result.stderr = str(
                        budget.get("reason")
                        or "diff budget exceeded"
                    )
                    try:
                        self._emit(
                            "DIFF_BUDGET",
                            result.stderr[:300],
                            task_id=task.id,
                            worker=worker.name,
                            payload=budget,
                        )
                    except Exception:
                        pass
                    try:
                        from utils.metrics import GLOBAL_METRICS
                        GLOBAL_METRICS.record("diff_budget_exceeded")
                    except Exception:
                        pass
                    return message, attempt_messages, commit_sha

            except Exception as exc:
                # Diff-budget is a safety gate. If it cannot be evaluated,
                # never continue as if verification succeeded.
                result.ok = False
                result.stderr = (
                    f"diff_budget_check_exception: "
                    f"{type(exc).__name__}: {exc}"
                )
                try:
                    self.log.write(result.stderr)
                except Exception:
                    pass
                return message, attempt_messages, commit_sha

        # Commit is part of the verified terminal path.
        # A commit failure must invalidate the successful execution.
        if result.ok and plan is not None and gitops is not None:
            try:
                commit_sha = gitops.commit_plan(
                    plan,
                    task=task,
                ) or ""
            except Exception as exc:
                result.ok = False
                result.stderr = (
                    f"git_commit_failed: "
                    f"{type(exc).__name__}: {exc}"
                )
                try:
                    self.log.write(result.stderr)
                except Exception:
                    pass
                return message, attempt_messages, commit_sha

            if not commit_sha:
                result.ok = False
                result.stderr = "git_commit_failed: empty commit SHA"
                try:
                    self.log.write(result.stderr)
                except Exception:
                    pass
                return message, attempt_messages, commit_sha

        if result.ok:
            try:
                self._reset_verify_fails(task)
            except Exception as exp:
                try:
                    self.log.write(
                        f"_reset_verify_fails: {type(exp).__name__}: {exp}"
                    )
                except Exception:
                    pass
            try:
                from utils.metrics import GLOBAL_METRICS
                meta_v = (
                    task.metadata
                    if isinstance(getattr(task, "metadata", None), dict)
                    else {}
                )
                lvl = int(
                    meta_v.get("verify_ladder")
                    or meta_v.get("verify_max_level")
                    or 0
                )
                GLOBAL_METRICS.record_verify_ladder(
                    success=True,
                    level=lvl,
                )
            except Exception:
                pass

        return message, attempt_messages, commit_sha

    def _quarantine_exhausted_task(
        self,
        task,
        *,
        error: str = "",
        worker: str = "",
        reason: str = "",
        category: str = "",
        gitops=None,
        before_snapshot=None,
        extra: dict | None = None,
    ):
        """Move task to quarantine after verify budget exhausted.

        Returns Path to quarantine JSON when written, else status string "ERROR".
        """
        msg = (reason or error or "verify budget exhausted").strip()
        failures: list[str] = []

        try:
            if gitops is not None and before_snapshot is not None:
                self._rollback_task(
                    gitops,
                    before_snapshot,
                    task,
                )
        except Exception as exp:
            failures.append(
                f"rollback: {type(exp).__name__}: {exp}"
            )

        try:
            self._save(
                task,
                "errors",
                {
                    "error": msg,
                    "attempts": getattr(task, "attempts", 0),
                    "quarantine": True,
                    "verify_budget": VERIFY_FAIL_MAX,
                    "category": category or "",
                    **(extra or {}),
                },
            )
        except Exception as exp:
            failures.append(
                f"save_errors: {type(exp).__name__}: {exp}"
            )

        try:
            ch = getattr(task, "channel", None) or "gpt"
            self.bus.move(
                ch,
                "processing",
                "errors",
                f"{task.id}.json",
            )
        except Exception as exp:
            failures.append(
                f"bus_move: {type(exp).__name__}: {exp}"
            )

        qpath = None
        try:
            from pathlib import Path as _P
            import json as _json
            import time as _time

            try:
                from core.config import BUS_ROOT
                base = _P(BUS_ROOT)
            except Exception:
                base = _P(".agentbus")

            qdir = base / "quarantine"
            qdir.mkdir(parents=True, exist_ok=True)
            qpath = qdir / f"{getattr(task, 'id', 'task')}.json"

            payload = {
                "id": getattr(task, "id", ""),
                "channel": getattr(task, "channel", ""),
                "project": getattr(task, "project", ""),
                "message": getattr(task, "message", ""),
                "files": list(getattr(task, "files", None) or []),
                "attempts": getattr(task, "attempts", 0),
                "error": msg,
                "metadata": {
                    **dict(getattr(task, "metadata", None) or {}),
                    "quarantined": True,
                    "category": category or "",
                    "verify_budget": VERIFY_FAIL_MAX,
                    **(extra or {}),
                },
                "ts": _time.time(),
            }
            if failures:
                payload["quarantine_warnings"] = list(failures)

            qpath.write_text(
                _json.dumps(
                    payload,
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
        except Exception as exp:
            failures.append(
                f"quarantine_write: {type(exp).__name__}: {exp}"
            )
            qpath = None

        if failures:
            detail = "; ".join(failures)[:800]
            try:
                self.log.write(
                    f"quarantine incomplete: {detail}"
                )
            except Exception:
                pass
            try:
                self._emit(
                    "QUARANTINE_INCOMPLETE",
                    detail,
                    task_id=getattr(task, "id", ""),
                    worker=worker,
                )
            except Exception:
                pass

        try:
            self._emit(
                "QUARANTINE",
                msg[:300],
                task_id=getattr(task, "id", ""),
                worker=worker,
            )
        except Exception:
            pass

        if qpath is None:
            return "ERROR"
        return qpath
