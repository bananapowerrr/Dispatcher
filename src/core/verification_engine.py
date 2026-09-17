# -*- coding: utf-8 -*-
"""VerificationEngine — единая точка проверки после execute.

Объединяет:
  - verify_policy (ladder + anti false-DONE)
  - syntax_guard / static_guard (если доступны)
  - run_command (pytest / py_compile / custom)

Результат всегда структурированный — runtime не должен гадать по stdout.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str = ""
    command: str = ""
    code: int | None = None
    duration_sec: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "passed": self.passed,
            "status": "passed" if self.passed else "failed",
            "detail": (self.detail or "")[:2000],
            "command": self.command or "",
            "code": self.code,
            "exit_code": self.code,
            "duration_sec": round(float(self.duration_sec or 0.0), 3),
        }


@dataclass
class VerificationReport:
    passed: bool
    checks: list[CheckResult] = field(default_factory=list)
    reason: str = ""
    risk: str = "low"  # low | medium | high | critical
    duration_sec: float = 0.0

    def summary_line(self) -> str:
        """One-line product summary for chat/history."""
        n = len(self.checks)
        ok_n = sum(1 for c in self.checks if c.passed)
        if self.passed:
            base = f"Verify PASS ({ok_n}/{n})" if n else "Verify PASS"
        else:
            failed = [c.name for c in self.checks if not c.passed]
            base = f"Verify FAIL ({ok_n}/{n})"
            if failed:
                base += ": " + ",".join(failed[:4])
            elif self.reason:
                base += f": {self.reason[:80]}"
        if self.duration_sec:
            base += f" · {self.duration_sec:.1f}s"
        if self.risk and self.risk != "low":
            base += f" · risk={self.risk}"
        return base

    def format_human(self) -> str:
        """Multi-line report for UI details."""
        lines = [self.summary_line()]
        for c in self.checks:
            mark = "✓" if c.passed else "✗"
            dur = f" ({c.duration_sec:.1f}s)" if c.duration_sec else ""
            lines.append(f"  {mark} {c.name}{dur}")
            if not c.passed and c.detail:
                lines.append(f"      {c.detail[:200].replace(chr(10), ' ')}")
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "reason": self.reason,
            "risk": self.risk,
            "duration_sec": round(float(self.duration_sec or 0.0), 3),
            "summary": self.summary_line(),
            "checks": [c.to_dict() for c in self.checks],
            # backward-compat map
            "check_map": {
                c.name: ("passed" if c.passed else "failed")
                for c in self.checks
            },
            "details": [
                {
                    "name": c.name,
                    "passed": c.passed,
                    "detail": c.detail[:2000],
                    "command": c.command,
                    "code": c.code,
                    "duration_sec": round(float(c.duration_sec or 0.0), 3),
                }
                for c in self.checks
            ],
        }


class VerificationEngine:
    """Run ladder of checks for a task against project_root."""

    def __init__(self, project_root: str | Path | None = None):
        self.project_root = Path(project_root) if project_root else Path.cwd()

    def prepare(self, raw: dict[str, Any]) -> dict[str, Any]:
        """Apply verify_policy (inject cmds / ladder). Mutates copy."""
        try:
            from core.verify_policy import apply_verify_policy
            return apply_verify_policy(dict(raw or {}))
        except Exception:
            return dict(raw or {})

    def run(self, raw: dict[str, Any], *, project_root: str | Path | None = None) -> VerificationReport:
        """Full verification pass. Never raises — returns passed=False on errors."""
        import time as _time
        _t0 = _time.monotonic()
        root = Path(project_root) if project_root else self.project_root
        raw = self.prepare(raw)
        meta = raw.get("metadata") if isinstance(raw.get("metadata"), dict) else {}
        verification = raw.get("verification") if isinstance(raw.get("verification"), dict) else {}
        checks: list[CheckResult] = []

        files = [str(f) for f in (raw.get("files") or []) if str(f).endswith(".py")]
        want_syntax = verification.get("syntax", True)
        want_tests = verification.get("tests", None)  # None = follow ladder
        ladder = int(meta.get("verify_ladder") or meta.get("verify_max_level") or 0)

        # --- L0/L1 syntax ---
        if want_syntax and (files or ladder >= 1):
            checks.append(self._check_syntax(root, files))

        # --- static guard (optional, fail closed only if AGENTBUS_STATIC_STRICT) ---
        strict_static = (os.getenv("AGENTBUS_STATIC_STRICT") or "").lower() in ("1", "true", "yes")
        if files and (ladder >= 2 or verification.get("security") or verification.get("lint")):
            checks.append(self._check_static(root, files, strict=strict_static))

        # --- commands from task.verify ---
        cmds = [str(c) for c in (raw.get("verify") or []) if c]
        require_tests = bool(want_tests) if want_tests is not None else ladder >= 2
        for cmd in cmds:
            checks.append(self._run_cmd(root, cmd, require_tests=require_tests and "pytest" in cmd.lower()))

        if not checks:
            # trivial task — nothing to verify
            rep = VerificationReport(passed=True, checks=[], reason="no_checks_trivial")
        else:
            failed = [c for c in checks if not c.passed]
            if failed:
                rep = VerificationReport(
                    passed=False,
                    checks=checks,
                    reason=failed[0].detail or f"{failed[0].name} failed",
                )
            else:
                rep = VerificationReport(passed=True, checks=checks, reason="all_passed")
        try:
            rep.duration_sec = max(0.0, _time.monotonic() - _t0)
        except Exception as exp:
            try:
                from utils.safe_log import warn
                warn("agentbus.verify", "duration_sec: %s", exp)
            except Exception:
                pass
        return finalize_report(rep)

    def _check_syntax(self, root: Path, files: list[str]) -> CheckResult:
        try:
            from core.verify import run_command
            if files:
                # limit
                safe = files[:20]
                joined = " ".join(f'"{f}"' for f in safe)
                cmd = f"python -m py_compile {joined}"
            else:
                cmd = "python -m compileall -q ."
            res = run_command(cmd, cwd=root, timeout=120, retries=1)
            return CheckResult(
                name="syntax",
                passed=bool(res.ok),
                detail=(res.output or "")[:1500],
                command=cmd,
                code=res.code,
            )
        except Exception as e:
            return CheckResult(name="syntax", passed=False, detail=str(e)[:500])

    def _check_static(self, root: Path, files: list[str], *, strict: bool) -> CheckResult:
        try:
            from safety.static_guard import check_paths
            paths = [root / f if not Path(f).is_absolute() else Path(f) for f in files[:30]]
            issues = check_paths(paths) if callable(check_paths) else []
            if issues:
                detail = "; ".join(
                    (getattr(i, "format", lambda: str(i))() if hasattr(i, "format") else str(i))
                    for i in issues[:5]
                )
                return CheckResult(
                    name="static",
                    passed=not strict,
                    detail=detail,
                )
            return CheckResult(name="static", passed=True, detail="clean")
        except Exception as e:
            return CheckResult(name="static", passed=True, detail=f"skipped: {e}")

    def _run_cmd(self, root: Path, cmd: str, *, require_tests: bool) -> CheckResult:
        try:
            from core.verify import run_command
            from core.verify_policy import detect_false_done
            res = run_command(cmd, cwd=root, timeout=300, retries=2)
            ok = bool(res.ok)
            detail = res.output or ""
            if ok and "pytest" in cmd.lower():
                bad = detect_false_done(detail, cmd, require_tests=require_tests)
                if bad:
                    ok = False
                    detail = f"{bad}\n{detail}"
            # Stable product names for risk + UI (not "cmd:pytest")
            low = cmd.lower()
            if "pytest" in low:
                cname = "pytest"
            elif "py_compile" in low or "compileall" in low:
                cname = "syntax"
            elif "mypy" in low or "typecheck" in low:
                cname = "typecheck"
            elif "ruff" in low or "lint" in low:
                cname = "lint"
            else:
                cname = "cmd:" + (cmd.split()[0][:40] if cmd.split() else "cmd")
            return CheckResult(
                name=cname,
                passed=ok,
                detail=detail[:2000],
                command=cmd,
                code=res.code,
            )
        except Exception as e:
            return CheckResult(name="cmd", passed=False, detail=str(e)[:500], command=cmd)


def gate_done(
    execution_ok: bool,
    report: VerificationReport | None,
    *,
    short_circuit: str | None = None,
) -> tuple[bool, str]:
    """DONE Gate: execution + verification must both succeed.

    Invariants (FC-11):
      - FAIL verification can NEVER become DONE
      - missing report is fail-closed (except explicit short_circuit)
      - short_circuit only for cache_hit / skill_success (deterministic paths)
    """
    if short_circuit in ("cache_hit", "skill_success"):
        # Still reject if an explicit FAIL report was supplied (defense in depth)
        if report is not None and not report.passed:
            return False, report.reason or "verification_failed_overrides_short_circuit"
        return True, f"short_circuit:{short_circuit}"
    if not execution_ok:
        return False, "execution_failed"
    if report is None:
        return False, "verification_missing"
    if not report.passed:
        return False, report.reason or "verification_failed"
    return True, "ok"


def embed_report(result: dict[str, Any], report: VerificationReport) -> dict[str, Any]:
    """Attach structured verification into a worker/result dict for TaskResult/UI."""
    out = dict(result or {})
    payload = report.to_dict()
    out["verification"] = payload
    out["ok"] = bool(out.get("ok", True)) and bool(report.passed)
    if not report.passed:
        out["ok"] = False
        out["status"] = "ERROR"
        err = report.reason or payload.get("summary") or "verification_failed"
        prev = str(out.get("error") or out.get("stderr") or "")
        if err and err not in prev:
            out["error"] = (prev + "\n" + err).strip() if prev else err
    else:
        if not out.get("status"):
            out["status"] = "DONE" if out.get("ok") else "ERROR"
    return out


def report_from_dict(data: dict[str, Any] | None) -> VerificationReport | None:
    """Rebuild VerificationReport from stored metadata (history/UI)."""
    if not isinstance(data, dict) or not data:
        return None
    checks: list[CheckResult] = []
    for c in (data.get("checks") or data.get("details") or []):
        if not isinstance(c, dict):
            continue
        checks.append(
            CheckResult(
                name=str(c.get("name") or "?"),
                passed=bool(c.get("passed") if "passed" in c else str(c.get("status")) == "passed"),
                detail=str(c.get("detail") or "")[:2000],
                command=str(c.get("command") or ""),
                code=c.get("code") if c.get("code") is not None else c.get("exit_code"),
                duration_sec=float(c.get("duration_sec") or 0),
            )
        )
    return VerificationReport(
        passed=bool(data.get("passed")),
        checks=checks,
        reason=str(data.get("reason") or ""),
        risk=str(data.get("risk") or "low"),
        duration_sec=float(data.get("duration_sec") or 0),
    )


def finalize_report(report: VerificationReport) -> VerificationReport:
    """Attach risk label before returning to runtime."""
    report.risk = summarize_risk(report)
    if not report.passed and not report.reason:
        failed = [c.name for c in report.checks if not c.passed]
        report.reason = "failed:" + ",".join(failed[:5]) if failed else "verification_failed"
    return report


def summarize_risk(report: VerificationReport) -> str:
    """Derive risk label from failed checks."""
    if report.passed:
        return "low"
    names = {c.name for c in report.checks if not c.passed}
    joined = " ".join(names).lower()
    if names & {"syntax", "static", "security"} or "static" in joined or "syntax" in joined:
        return "high"
    if "pytest" in joined or "test" in joined or "typecheck" in joined or "lint" in joined:
        return "medium"
    if report.reason and "false_DONE" in report.reason:
        return "high"
    return "medium"
