# -*- coding: utf-8 -*-
"""MockWorker — offline scenarios for E2E orchestration tests (Sprint A).

No Ollama / Aider / network. Deterministic outcomes for pipeline testing.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable

from core.worker_api import WorkerResult


# Scenario names
SUCCESS = "SUCCESS"
VERIFY_FAIL = "VERIFY_FAIL"
TIMEOUT = "TIMEOUT"
CRASH = "CRASH"
RETRY_SUCCESS = "RETRY_SUCCESS"
INVALID_OUTPUT = "INVALID_OUTPUT"
EMPTY_OUTPUT = "EMPTY_OUTPUT"
PATCH_OK = "PATCH_OK"


@dataclass
class MockScenario:
    name: str
    ok: bool = True
    stdout: str = ""
    stderr: str = ""
    latency: float = 0.01
    tokens: int = 10
    raise_exc: type[BaseException] | None = None
    files_changed: dict[str, str] = field(default_factory=dict)
    meta: dict[str, Any] = field(default_factory=dict)


SCENARIOS: dict[str, MockScenario] = {
    SUCCESS: MockScenario(
        SUCCESS,
        ok=True,
        stdout="mock: applied small fix\n",
        files_changed={"demo.py": "def ok():\n    return 1\n"},
        meta={"scenario": SUCCESS},
    ),
    PATCH_OK: MockScenario(
        PATCH_OK,
        ok=True,
        stdout="mock: patch written\n",
        files_changed={"demo.py": "x = 1\n"},
        meta={"scenario": PATCH_OK, "patch": True},
    ),
    VERIFY_FAIL: MockScenario(
        VERIFY_FAIL,
        ok=True,  # worker "succeeds" but leaves broken code for verify
        stdout="mock: wrote broken code\n",
        files_changed={"demo.py": "def broken(\n"},  # syntax error
        meta={"scenario": VERIFY_FAIL, "expect_verify_fail": True},
    ),
    TIMEOUT: MockScenario(
        TIMEOUT,
        ok=False,
        stderr="mock: timeout",
        latency=0.05,
        meta={"scenario": TIMEOUT, "timeout": True},
    ),
    CRASH: MockScenario(
        CRASH,
        ok=False,
        raise_exc=RuntimeError,
        stderr="mock: crash",
        meta={"scenario": CRASH},
    ),
    RETRY_SUCCESS: MockScenario(
        RETRY_SUCCESS,
        ok=True,
        stdout="mock: ok on retry path\n",
        files_changed={"demo.py": "def ok():\n    return 2\n"},
        meta={"scenario": RETRY_SUCCESS, "retry_aware": True},
    ),
    INVALID_OUTPUT: MockScenario(
        INVALID_OUTPUT,
        ok=True,
        stdout="<<<not a valid patch>>>",
        meta={"scenario": INVALID_OUTPUT, "invalid": True},
    ),
    EMPTY_OUTPUT: MockScenario(
        EMPTY_OUTPUT,
        ok=True,
        stdout="",
        meta={"scenario": EMPTY_OUTPUT, "empty": True},
    ),
}


class MockWorker:
    """WorkerBackend-compatible mock."""

    name = "mock_worker"

    def __init__(
        self,
        scenario: str = SUCCESS,
        *,
        attempt_map: dict[int, str] | None = None,
    ) -> None:
        self.scenario = scenario
        self.attempt_map = dict(attempt_map or {})
        self.calls = 0
        self.history: list[str] = []

    def capabilities(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "local": True,
            "mock": True,
            "scenarios": list(SCENARIOS.keys()),
        }

    def health(self) -> dict[str, Any]:
        return {"ok": True, "name": self.name}

    def estimate(self, task: Any) -> float:
        return 0.01

    def execute(self, task: Any, context: dict[str, Any] | None = None) -> WorkerResult:
        self.calls += 1
        attempt = 1
        if isinstance(task, dict):
            attempt = int(task.get("attempts") or task.get("metadata", {}).get("attempt") or 1)
        else:
            attempt = int(getattr(task, "attempts", 1) or 1)

        scen_name = self.attempt_map.get(attempt, self.scenario)
        # RETRY_SUCCESS: fail first attempt
        if self.scenario == RETRY_SUCCESS and attempt <= 1 and attempt not in self.attempt_map:
            scen_name = TIMEOUT

        scen = SCENARIOS.get(scen_name) or SCENARIOS[SUCCESS]
        self.history.append(scen_name)

        if scen.raise_exc:
            raise scen.raise_exc(scen.stderr or "mock crash")

        time.sleep(min(0.05, float(scen.latency)))
        meta = dict(scen.meta)
        meta["files_changed"] = dict(scen.files_changed)
        meta["attempt"] = attempt
        # apply files if project_root in context
        ctx = context or {}
        root = ctx.get("project_root")
        if root and scen.files_changed:
            from pathlib import Path
            base = Path(root)
            for rel, content in scen.files_changed.items():
                path = base / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
        return WorkerResult(
            ok=scen.ok,
            stdout=scen.stdout,
            stderr=scen.stderr,
            latency=scen.latency,
            tokens=scen.tokens,
            meta=meta,
        )


def run_scenario(name: str, task: Any = None, **kw: Any) -> WorkerResult:
    return MockWorker(name, **kw).execute(task or {"id": "t", "attempts": 1}, {})
