# -*- coding: utf-8 -*-
"""Offline tests for post-failure meta decomposition (no Ollama required)."""
from __future__ import annotations

import os

import pytest


def test_heuristic_split_multi_file(monkeypatch):
    monkeypatch.setenv("AGENTBUS_META", "0")
    monkeypatch.setenv("AGENTBUS_META_DECOMPOSE", "1")
    from skills.meta_decompose import plan_subtasks

    r = plan_subtasks(
        "Refactor module",
        files=["a.py", "b.py", "c.py"],
        failure_reason="no_changes_and_no_verification",
    )
    assert r.ok
    assert r.source == "heuristic"
    assert len(r.subtasks) >= 2
    assert all(st.files for st in r.subtasks)


def test_disabled_returns_skipped(monkeypatch):
    monkeypatch.setenv("AGENTBUS_META", "0")
    monkeypatch.setenv("AGENTBUS_META_DECOMPOSE", "0")
    from skills.meta_decompose import plan_subtasks

    r = plan_subtasks("x", files=["a.py"])
    assert r.ok is False
    assert r.source == "skipped"


def test_normalize_rejects_path_escape(monkeypatch):
    monkeypatch.setenv("AGENTBUS_META_DECOMPOSE", "1")
    monkeypatch.setenv("AGENTBUS_META", "0")
    from skills.meta_decompose import _normalize_subtasks

    subs = _normalize_subtasks(
        [
            {"message": "do safe work on util", "files": ["src/util.py", "../etc/passwd", "/abs"]},
            {"message": "too", "files": []},  # too short message
        ]
    )
    assert len(subs) == 1
    assert subs[0].files == ["src/util.py"]


def test_try_decompose_skips_subtask(monkeypatch):
    monkeypatch.setenv("AGENTBUS_META_DECOMPOSE", "1")
    from skills.meta_decompose import try_decompose_failed_task
    from types import SimpleNamespace

    task = SimpleNamespace(
        id="child1",
        message="fix",
        files=["a.py"],
        channel="gpt",
        project="",
        metadata={"is_subtask": True, "parent_id": "p"},
    )
    runtime = SimpleNamespace(bus=SimpleNamespace(root="."), log=SimpleNamespace(write=lambda *a, **k: None))
    meta = try_decompose_failed_task(runtime, task, failure_reason="x")
    assert meta.get("meta_decompose_source") == "skipped_subtask"


def test_empty_message_is_not_decomposed(monkeypatch):
    """Пустую задачу декомпозировать нечем.

    Регрессия из живого прогона: задача с пустым message ушла в 1.5B с одним
    лишь failure_reason, и модель выдумала посторонние подзадачи
    ("Review the logs ... payment gate"). Мусор в очереди хуже отказа.
    """
    monkeypatch.setenv("AGENTBUS_META", "1")
    monkeypatch.setenv("AGENTBUS_META_DECOMPOSE", "1")
    from skills.meta_decompose import plan_subtasks

    r = plan_subtasks("", files=["a.py"], failure_reason="paid_gate_blocked")
    assert r.ok is False
    assert r.subtasks == []
    assert r.error == "empty_task_message"
