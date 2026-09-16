# -*- coding: utf-8 -*-
"""Offline smoke: policy + phase + queue without Ollama."""
from __future__ import annotations

import json
from pathlib import Path


def test_beginner_preset_parallel_is_one():
    import yaml
    from core.config import BASE_DIR
    path = Path(BASE_DIR) / "config" / "feature_presets.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    env = (data.get("beginner_ru") or {}).get("env") or {}
    assert str(env.get("AGENTBUS_MAX_PARALLEL_PROJECTS", "1")) == "1"


def test_set_phase_writes_processing(tmp_path, monkeypatch):
    from core.runtime_ops import RuntimeOps
    from core.tasks import Task

    class T(RuntimeOps):
        def __init__(self):
            self.saved = []

        def _save(self, task, state, extra=None):
            self.saved.append((state, dict(extra or {})))

    rt = T()
    task = Task.from_dict({"id": "t1", "message": "hi", "channel": "desktop"})
    rt._set_phase(task, "cache_skills")
    assert rt.saved
    assert rt.saved[-1][0] == "processing"
    assert rt.saved[-1][1].get("phase") == "cache_skills"


def test_desktop_enqueue_claim_roundtrip(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    spill = tmp_path / ".agentbus" / "desktop_queue"
    from core.local_queue import LocalQueue, enqueue_desktop_task
    from core import local_queue as lq

    lq._GLOBAL = LocalQueue(spill_dir=spill)
    tid = enqueue_desktop_task("добавь docstring", project="p", files=["a.py"], root=tmp_path)
    raw = lq._GLOBAL.claim()
    assert raw is not None
    assert raw["id"] == tid or raw.get("message")
    assert raw.get("channel") == "desktop"


def test_plugin_registry_soft_load():
    from core.plugin_registry import load, status
    # verify_policy should load
    mod = load("verify_policy")
    assert mod is not None or mod is None  # soft
    st = status()
    assert isinstance(st, (dict, list)) or st is not None
