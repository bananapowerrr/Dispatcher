# -*- coding: utf-8 -*-
"""Minimal offline E2E harness for file-bus + verify + quarantine paths.

No Ollama, no Aider, no network. Uses tmp directories and optional mock worker.
"""
from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path
from typing import Any, Callable


def init_git_repo(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init"], cwd=str(root), capture_output=True, check=True)
    subprocess.run(
        ["git", "config", "user.email", "agentbus@test"],
        cwd=str(root),
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "AgentBus Test"],
        cwd=str(root),
        capture_output=True,
    )
    (root / "README.md").write_text("# e2e\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=str(root), capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=str(root),
        capture_output=True,
        check=True,
    )


def ensure_bus_channels(bus_root: Path, channel: str = "gpt") -> None:
    for stage in ("incoming", "processing", "done", "errors", "deferred"):
        (bus_root / "channels" / channel / stage).mkdir(parents=True, exist_ok=True)


def write_task(
    bus_root: Path,
    *,
    task_id: str,
    message: str,
    files: list[str] | None = None,
    channel: str = "gpt",
    project: str = "",
    metadata: dict[str, Any] | None = None,
) -> Path:
    ensure_bus_channels(bus_root, channel)
    payload = {
        "id": task_id,
        "message": message,
        "files": list(files or []),
        "project": project,
        "channel": channel,
        "status": "PENDING",
        "attempts": 0,
        "verify": [],
        "metadata": metadata or {"source": "e2e"},
    }
    path = bus_root / "channels" / channel / "incoming" / f"{task_id}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def claim_task(bus_root: Path, task_id: str, channel: str = "gpt") -> Path:
    from core.bus import FileBus

    bus = FileBus(bus_root, (channel,))
    bus.ensure()
    ok = bus.move(channel, "incoming", "processing", f"{task_id}.json")
    if not ok:
        raise RuntimeError(f"claim failed for {task_id}")
    return bus_root / "channels" / channel / "processing" / f"{task_id}.json"


def finish_task(
    bus_root: Path,
    task_id: str,
    *,
    channel: str = "gpt",
    state: str = "done",
    extra: dict[str, Any] | None = None,
) -> Path:
    from core.bus import FileBus

    bus = FileBus(bus_root, (channel,))
    bus.ensure()
    proc = bus_root / "channels" / channel / "processing" / f"{task_id}.json"
    if proc.is_file() and extra:
        data = json.loads(proc.read_text(encoding="utf-8"))
        data.update(extra)
        proc.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    ok = bus.move(channel, "processing", state, f"{task_id}.json")
    if not ok:
        raise RuntimeError(f"finish move to {state} failed")
    return bus_root / "channels" / channel / state / f"{task_id}.json"


def run_verify_guards(
    files: list[str],
    *,
    root: Path,
) -> tuple[bool, str]:
    """L0 + L0.5 only (syntax + static)."""
    from safety.syntax_guard import guard_or_error as syn
    from safety.static_guard import guard_or_error as st

    ok, err = syn(files, root=root)
    if not ok:
        return False, err
    return st(files, root=root)


def simulate_verify_fail_quarantine(
    bus_root: Path,
    project: Path,
    *,
    task_id: str = "e2e-bad",
    channel: str = "gpt",
) -> dict[str, Any]:
    """Write bad Python → claim → static fail → quarantine copy + errors.

    Does not start full Runtime/Ollama — exercises the critical offline path.
    """
    from types import SimpleNamespace

    bad = project / "bad_mod.py"
    bad.write_text(
        "def f():\n    try:\n        x = 1\n    except:\n        pass\n    eval('1+1')\n",
        encoding="utf-8",
    )
    write_task(
        bus_root,
        task_id=task_id,
        message="fix module",
        files=["bad_mod.py"],
        channel=channel,
        project=str(project),
        metadata={"source": "e2e", "complexity": 3, "consecutive_verify_fails": 3},
    )
    claim_task(bus_root, task_id, channel)
    ok, err = run_verify_guards(["bad_mod.py"], root=project)
    assert not ok, "static/syntax should fail on bad_mod"
    # quarantine via Runtime method
    from core.runtime import Runtime

    rt = Runtime.__new__(Runtime)
    rt.worker_id = "e2e"
    rt.log = SimpleNamespace(write=lambda s: None)
    rt._emit = lambda *a, **k: None
    rt._rollback_task = lambda *a, **k: []
    rt._cleanup_task_git_branch = lambda *a, **k: None
    task = SimpleNamespace(
        id=task_id,
        channel=channel,
        project=str(project),
        message="fix module",
        files=["bad_mod.py"],
        attempts=3,
        verify=["pytest -q"],
        metadata={"consecutive_verify_fails": 3, "source": "e2e"},
    )
    # BUS_ROOT for quarantine path
    import core.config as cfg

    old = getattr(cfg, "BUS_ROOT", None)
    cfg.BUS_ROOT = bus_root  # type: ignore
    try:
        qpath = rt._quarantine_exhausted_task(
            task,
            reason=err[:500],
            category="CODE_ERROR",
            gitops=None,
            before_snapshot=None,
            extra={"final": "BLOCKED"},
        )
    finally:
        if old is not None:
            cfg.BUS_ROOT = old
    finish_task(
        bus_root,
        task_id,
        channel=channel,
        state="errors",
        extra={"error": err, "quarantined": True},
    )
    return {
        "verify_ok": ok,
        "error": err,
        "quarantine": str(qpath) if qpath else "",
        "errors_json": str(
            bus_root / "channels" / channel / "errors" / f"{task_id}.json"
        ),
    }


def simulate_happy_skill_path(
    bus_root: Path,
    project: Path,
    *,
    task_id: str = "e2e-ok",
    channel: str = "gpt",
) -> dict[str, Any]:
    """incoming → processing → static ok on clean file → done."""
    clean = project / "clean.py"
    clean.write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    write_task(
        bus_root,
        task_id=task_id,
        message="check clean",
        files=["clean.py"],
        channel=channel,
        project=str(project),
    )
    claim_task(bus_root, task_id, channel)
    ok, err = run_verify_guards(["clean.py"], root=project)
    if ok:
        finish_task(bus_root, task_id, channel=channel, state="done", extra={"ok": True})
    else:
        finish_task(
            bus_root, task_id, channel=channel, state="errors", extra={"error": err}
        )
    return {"verify_ok": ok, "error": err}
