# -*- coding: utf-8 -*-
"""Offline pipeline: cache → skills → meta → router (no LLM, no network)."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from meta_classifier import classify_task, enrich_task_metadata
from skills import SkillRegistry
from solution_cache import SolutionCache
from tools import ToolRegistry


def test_pipeline_skill_hit_skips_llm(tmp_path: Path):
    """format_code skill matches → no need for worker."""
    tools = ToolRegistry(tmp_path)
    skills = SkillRegistry(tools)
    msg = "отформатируй код"
    name = skills.match(msg)
    assert name == "format_code"
    # execute may miss black/isort — still returns dict
    out = skills.execute(name, path=str(tmp_path))
    assert "success" in out


def test_pipeline_cache_roundtrip(tmp_path: Path):
    cache = SolutionCache(cache_path=str(tmp_path / "c.json"), max_entries=10)
    task = SimpleNamespace(
        message="add noop comment",
        files=[],
        project="demo",
        verify=[],
    )
    assert cache.get(task, require_content_match=False) is None
    cache.put(task, solution={"summary": "done", "result": {"ok": True}, "method": "skill"})
    hit = cache.get(task, require_content_match=False)
    assert hit is not None
    sol = hit.get("solution") or {}
    assert sol.get("summary") == "done"
    assert sol.get("method") == "skill"


def test_pipeline_meta_then_router_fields():
    raw = {"message": "удали неиспользуемые импорты", "files": ["a.py"]}
    enriched = enrich_task_metadata(raw)
    meta = enriched.get("metadata") or {}
    assert meta.get("task_type") in ("cleanup", "general", "docs", "typing", "bugfix", "refactor", "test", "feature")
    assert 1 <= int(enriched.get("complexity") or meta.get("complexity") or 3) <= 5
    assert meta.get("risk_level") in ("low", "medium", "high")
    assert meta.get("suggested_worker")


def test_pipeline_complex_goes_to_llm_not_skill():
    skills = SkillRegistry(ToolRegistry(Path(".")))
    assert skills.match("рефакторинг архитектуры всего проекта") is None


def test_pipeline_bus_write_claim_shape(tmp_path: Path):
    """Task JSON shape that runtime expects."""
    from bus import FileBus
    import json

    bus = FileBus(tmp_path, ("gpt",))
    bus.ensure()
    payload = {
        "id": "t-offline-1",
        "message": "format code",
        "files": [],
        "project": "demo",
        "channel": "gpt",
        "status": "PENDING",
        "metadata": {"source": "test"},
    }
    path = bus.write("gpt", "incoming", "t-offline-1.json", json.dumps(payload, ensure_ascii=False))
    assert path.is_file()
    assert bus.move("gpt", "incoming", "processing", "t-offline-1.json") is True
    data = json.loads((tmp_path / "channels/gpt/processing/t-offline-1.json").read_text(encoding="utf-8"))
    assert data["id"] == "t-offline-1"
