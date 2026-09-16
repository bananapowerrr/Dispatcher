# -*- coding: utf-8 -*-
"""Offline e2e: reclaim stuck processing + cache miss after git HEAD change.

No LLM, no network, no full dispatcher loop.
"""
from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path
from types import SimpleNamespace

import pytest


def _make_bus(tmp_path: Path, channel: str = "gpt"):
    from core.bus import FileBus

    bus = FileBus(tmp_path, (channel,))
    bus.ensure()
    return bus


def test_e2e_filebus_stale_processing_requeued(tmp_path: Path):
    """processing + old mtime → reclaim → incoming (attempts bumped)."""
    from core.reclaim import reclaim_stuck

    channel = "gpt"
    bus = _make_bus(tmp_path, channel)
    tid = "e2e-stuck-1"
    name = f"{tid}.json"
    payload = {
        "id": tid,
        "message": "noop reclaim test",
        "files": [],
        "attempts": 1,
        "channel": channel,
        "metadata": {"complexity": 2},
    }
    bus.write(channel, "processing", name, json.dumps(payload, ensure_ascii=False))
    proc = bus.paths(channel)["processing"] / name
    old = time.time() - 50_000
    os.utime(proc, (old, old))

    results = reclaim_stuck(
        processing_dir=bus.paths(channel)["processing"],
        incoming_dir=bus.paths(channel)["incoming"],
        errors_dir=bus.paths(channel)["errors"],
        channel=channel,
        bus_move=bus.move,
        max_attempts=3,
        base_sec=60,
        max_sec=120,
    )
    assert results and results[0]["moved"] is True
    assert results[0]["action"] == "REQUEUE"
    assert not proc.exists()
    incoming = bus.paths(channel)["incoming"] / name
    assert incoming.is_file()
    raw = json.loads(incoming.read_text(encoding="utf-8"))
    assert int(raw.get("attempts") or 0) >= 2
    assert (raw.get("metadata") or {}).get("reclaim_reason") == "stuck_no_heartbeat"


def test_e2e_filebus_stale_max_attempts_to_errors(tmp_path: Path):
    from core.reclaim import reclaim_stuck

    channel = "gpt"
    bus = _make_bus(tmp_path, channel)
    tid = "e2e-dead"
    name = f"{tid}.json"
    bus.write(
        channel,
        "processing",
        name,
        json.dumps(
            {
                "id": tid,
                "message": "dead",
                "attempts": 3,
                "metadata": {"complexity": 2},
            },
            ensure_ascii=False,
        ),
    )
    proc = bus.paths(channel)["processing"] / name
    os.utime(proc, (time.time() - 50_000, time.time() - 50_000))

    results = reclaim_stuck(
        processing_dir=bus.paths(channel)["processing"],
        incoming_dir=bus.paths(channel)["incoming"],
        errors_dir=bus.paths(channel)["errors"],
        channel=channel,
        bus_move=bus.move,
        max_attempts=3,
        base_sec=60,
        max_sec=120,
    )
    assert results[0]["action"] == "ERROR"
    assert list(bus.paths(channel)["errors"].glob("*.json"))
    assert not (bus.paths(channel)["processing"] / name).exists()


def test_e2e_runtime_recover_stale_via_mixin(tmp_path: Path, monkeypatch):
    """RuntimeOps._recover_stale_processing moves via bus with adaptive reclaim."""
    from core.bus import FileBus
    from core.runtime import RuntimeOps

    channel = "gpt"
    bus = FileBus(tmp_path, (channel,))
    bus.ensure()
    tid = "e2e-rt-1"
    name = f"{tid}.json"
    bus.write(
        channel,
        "processing",
        name,
        json.dumps(
            {
                "id": tid,
                "message": "via runtime",
                "attempts": 0,
                "metadata": {"complexity": 1},
            },
            ensure_ascii=False,
        ),
    )
    proc = bus.paths(channel)["processing"] / name
    os.utime(proc, (time.time() - 50_000, time.time() - 50_000))

    class _Log:
        def write(self, msg: str) -> None:
            self.last = msg

    class Mini(RuntimeOps):
        def __init__(self):
            self.bus = bus
            self.log = _Log()
            self.worker_id = "test-worker"

        def _active_channels(self):
            return [channel]

        def _emit(self, *a, **k):
            pass

    monkeypatch.setenv("AGENTBUS_STUCK_BASE_SEC", "60")
    monkeypatch.setenv("AGENTBUS_STUCK_TIMEOUT_MAX", "120")
    # force low base inside reclaim via kwargs in method — method uses config;
    # stamp task very old so any timeout works
    n = Mini()._recover_stale_processing(stale_seconds=60)
    assert n >= 1
    assert (bus.paths(channel)["incoming"] / name).is_file() or list(
        bus.paths(channel)["errors"].glob("*.json")
    )


def test_e2e_cache_hit_then_miss_after_commit(tmp_path: Path, monkeypatch):
    """Full offline path: put at HEAD1 → hit; commit → miss (no false DONE)."""
    monkeypatch.setenv("AGENTBUS_CACHE_GIT", "1")
    from intelligence.solution_cache import SolutionCache

    repo = tmp_path / "proj"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "t@t.com"], cwd=repo, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "config", "user.name", "T"], cwd=repo, check=True, capture_output=True
    )
    (repo / "mod.py").write_text("v = 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "mod.py"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "c1"], cwd=repo, check=True, capture_output=True
    )

    cache = SolutionCache(cache_path=tmp_path / "sc.json", max_entries=20, ttl_seconds=86400)
    task = SimpleNamespace(
        message="add docstring to mod",
        files=["mod.py"],
        project="proj",
        verify=["pytest -q"],
    )
    cache.put(
        task,
        {"method": "llm", "worker": "aider", "summary": "done at c1"},
        project_root=repo,
        file_snapshots={"mod.py": '"""doc"""\nv = 1\n'},
    )
    assert cache.get(task, project_root=repo, require_content_match=False) is not None

    (repo / "mod.py").write_text("v = 2\n", encoding="utf-8")
    subprocess.run(["git", "add", "mod.py"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "c2"], cwd=repo, check=True, capture_output=True
    )
    assert cache.get(task, project_root=repo, require_content_match=False) is None


def test_e2e_fresh_processing_not_reclaimed(tmp_path: Path):
    from core.reclaim import reclaim_stuck

    channel = "gpt"
    bus = _make_bus(tmp_path, channel)
    name = "fresh.json"
    bus.write(
        channel,
        "processing",
        name,
        json.dumps({"id": "fresh", "attempts": 0, "metadata": {"complexity": 5}}),
    )
    results = reclaim_stuck(
        processing_dir=bus.paths(channel)["processing"],
        incoming_dir=bus.paths(channel)["incoming"],
        errors_dir=bus.paths(channel)["errors"],
        channel=channel,
        bus_move=bus.move,
        max_attempts=3,
        base_sec=300,
        max_sec=1800,
    )
    assert results == []
    assert (bus.paths(channel)["processing"] / name).is_file()
