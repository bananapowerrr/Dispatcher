# -*- coding: utf-8 -*-
"""Offline pipeline E2E: Task → MockWorker → Verify → DONE/ERROR (Sprint A).

Does not start full Runtime. Exercises contracts: claim, execute, verify gate, finish.
"""
from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core.mock_worker import (
    MockWorker,
    SUCCESS,
    VERIFY_FAIL,
    TIMEOUT,
    CRASH,
    EMPTY_OUTPUT,
    RETRY_SUCCESS,
    INVALID_OUTPUT,
)
from core.worker_api import WorkerResult


@dataclass
class PipelineResult:
    task_id: str
    final_status: str  # DONE | ERROR | RETRY
    attempts: int = 1
    worker_ok: bool = False
    verify_passed: bool | None = None
    verification: dict[str, Any] = field(default_factory=dict)
    events: list[str] = field(default_factory=list)
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "final_status": self.final_status,
            "attempts": self.attempts,
            "worker_ok": self.worker_ok,
            "verify_passed": self.verify_passed,
            "verification": self.verification,
            "events": list(self.events),
            "error": self.error,
        }


def _emit(events: list[str], name: str) -> None:
    events.append(name)
    try:
        from utils.pipeline_events import (
            task_claimed,
            task_started,
            verify_started,
            verify_passed,
            verify_failed,
            task_done,
            task_error,
        )
        # lightweight — only for known names
    except Exception:
        pass


def run_pipeline(
    *,
    project_root: Path,
    bus_root: Path | None = None,
    scenario: str = SUCCESS,
    message: str = "mock task",
    files: list[str] | None = None,
    max_attempts: int = 2,
    channel: str = "e2e",
) -> PipelineResult:
    """Run a single offline pipeline with MockWorker + VerificationEngine."""
    from core.e2e_harness import ensure_bus_channels, write_task, claim_task
    from core.verification_engine import VerificationEngine, finalize_report, summarize_risk
    from core.tasks import Task

    bus_root = bus_root or project_root / ".agentbus_e2e"
    bus_root = Path(bus_root)
    project_root = Path(project_root)
    project_root.mkdir(parents=True, exist_ok=True)
    tid = "e2e_" + uuid.uuid4().hex[:10]
    events: list[str] = []
    try:
        from utils.task_trace import GLOBAL_TRACES
        _tr = GLOBAL_TRACES.start(tid, project_id=str(project_root), attempt=1, worker_id="mock")
    except Exception:
        _tr = None

    write_task(
        bus_root,
        task_id=tid,
        message=message,
        files=list(files or ["demo.py"]),
        channel=channel,
        project=str(project_root),
        metadata={"source": "pipeline_e2e", "scenario": scenario},
    )
    events.append("TASK_CREATED")
    claim_task(bus_root, tid, channel=channel)
    events.append("TASK_CLAIMED")
    if _tr:
        try:
            _tr.add("TASK_CLAIMED")
        except Exception:
            pass
    events.append("TASK_STARTED")

    worker = MockWorker(scenario)
    if scenario == RETRY_SUCCESS:
        # attempt 1 fails (timeout), attempt 2+ succeeds
        worker = MockWorker(RETRY_SUCCESS, attempt_map={1: TIMEOUT, 2: SUCCESS})

    attempts = 0
    last_verify: dict[str, Any] = {}
    worker_ok = False
    verify_passed: bool | None = None
    final = "ERROR"
    err = ""

    while attempts < max_attempts:
        attempts += 1
        task_dict = {
            "id": tid,
            "message": message,
            "files": list(files or ["demo.py"]),
            "attempts": attempts,
            "metadata": {"scenario": scenario},
        }
        events.append("WORKER_STARTED")
        try:
            result: WorkerResult = worker.execute(
                task_dict, context={"project_root": str(project_root)}
            )
            worker_ok = bool(result.ok)
        except Exception as exc:
            worker_ok = False
            err = f"{type(exc).__name__}: {exc}"
            events.append("WORKER_CRASH")
            result = WorkerResult(ok=False, stderr=err)
        events.append("WORKER_FINISHED")

        if not worker_ok:
            if attempts < max_attempts:
                events.append("RETRY")
                continue
            final = "ERROR"
            events.append("TASK_ERROR")
            break

        # verification — lightweight AST syntax for offline E2E (avoids shell-quote issues)
        events.append("VERIFY_STARTED")
        from core.verification_engine import VerificationReport, CheckResult, finalize_report
        file_list = list(files or ["demo.py"])
        syn_ok = True
        detail = ""
        try:
            import ast as _ast
            for rel in file_list:
                fp = project_root / rel
                if not fp.is_file():
                    syn_ok = False
                    detail = f"missing:{rel}"
                    break
                if str(rel).endswith(".py"):
                    _ast.parse(fp.read_text(encoding="utf-8"))
        except SyntaxError as se:
            syn_ok = False
            detail = f"syntax:{se}"
        except Exception as e:
            syn_ok = False
            detail = str(e)
        report = finalize_report(
            VerificationReport(
                passed=syn_ok,
                checks=[CheckResult(name="syntax", passed=syn_ok, detail=detail[:500], code=0 if syn_ok else 1)],
                reason="" if syn_ok else detail,
            )
        )
        last_verify = report.to_dict()
        verify_passed = bool(report.passed)
        if report.passed:
            events.append("VERIFY_PASSED")
            # finish done
            try:
                from core.bus import FileBus
                FileBus(bus_root, (channel,)).move(channel, "processing", "done", f"{tid}.json")
            except Exception:
                # ensure done dir
                done = bus_root / "channels" / channel / "done"
                done.mkdir(parents=True, exist_ok=True)
                src = bus_root / "channels" / channel / "processing" / f"{tid}.json"
                if src.is_file():
                    src.replace(done / f"{tid}.json")
            events.append("TASK_DONE")
            final = "DONE"
            break
        events.append("VERIFY_FAILED")
        if attempts < max_attempts:
            events.append("RETRY")
            continue
        try:
            from core.bus import FileBus
            FileBus(bus_root, (channel,)).move(channel, "processing", "errors", f"{tid}.json")
        except Exception:
            err_dir = bus_root / "channels" / channel / "errors"
            err_dir.mkdir(parents=True, exist_ok=True)
            src = bus_root / "channels" / channel / "processing" / f"{tid}.json"
            if src.is_file():
                src.replace(err_dir / f"{tid}.json")
        events.append("TASK_ERROR")
        final = "ERROR"
        err = report.reason or "verify_failed"
        break

    if _tr is not None:
        try:
            from utils.task_trace import GLOBAL_TRACES as _GT
            _GT.complete(tid, final)
        except Exception:
            pass
    return PipelineResult(
        task_id=tid,
        final_status=final,
        attempts=attempts,
        worker_ok=worker_ok,
        verify_passed=verify_passed,
        verification=last_verify,
        events=events,
        error=err,
    )
