# -*- coding: utf-8 -*-
"""Day 16: worker_route product surface (doctor/chat) without replacing select_executor."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest


def _w(name: str, *, provider: str = "ollama", enabled: bool = True, role: str = "code"):
    return SimpleNamespace(
        name=name,
        provider=provider,
        enabled=enabled,
        role=role,
        model="qwen2.5-coder:7b",
        timeout=120,
        max_parallel=1,
        harness="aider",
        priority=50,
    )


def test_route_for_task_with_workers():
    from core.worker_route_surface import route_for_task

    workers = [
        _w("aider_local", provider="ollama"),
        _w("mock", provider="mock", role="test"),
    ]
    d = route_for_task("Создай файл test.txt", workers=workers, include_diagnostics=False)
    assert isinstance(d, dict)
    assert "primary" in d
    assert "chain" in d
    assert "reasons" in d
    # with workers, should pick something or explain why not
    assert d.get("primary") or d.get("reasons")


def test_format_route_for_chat_shape():
    from core.worker_route_surface import format_route_for_chat

    workers = [_w("aider_local")]
    text = format_route_for_chat("fix auth", workers=workers)
    assert "WORKER ROUTE" in text
    assert "primary:" in text


def test_format_route_for_doctor():
    from core.worker_route_surface import format_route_for_doctor

    text = format_route_for_doctor(workers=[_w("aider_local")])
    assert "WORKER ROUTE" in text


def test_next_fallback_after_error():
    from core.worker_route_surface import next_fallback_after_error

    workers = [_w("aider_local"), _w("opencode_zen", provider="ollama")]
    d = next_fallback_after_error(["aider_local"], error="Connection refused", workers=workers)
    assert isinstance(d, dict)
    assert "primary" in d or "reasons" in d


def test_does_not_import_runtime_executor():
    """Surface must not pull runtime FSM modules at import time."""
    import core.worker_route_surface as s
    src = Path(s.__file__).read_text(encoding="utf-8")
    assert "select_executor" not in src or "does_not_replace" in src
    # no runtime claim loop
    assert "runtime.py" not in src
    assert "claim(" not in src


def test_diagnose_source_wires_route():
    roots = [
        Path(__file__).resolve().parents[1] / "src" / "utils" / "diagnose.py",
        Path("/home/workdir/artifacts/src/utils/diagnose.py"),
        Path("/home/workdir/artifacts/diagnose.py"),
    ]
    src = ""
    for p in roots:
        if p.is_file():
            src = p.read_text(encoding="utf-8")
            break
    assert src
    assert "format_route_for_doctor" in src
    assert "worker_route_surface" in src


def test_route_surface_summary():
    from core.worker_route_surface import route_surface_summary

    s = route_surface_summary()
    assert s["does_not_replace"] == "router.select_executor"
    assert "doctor" in s["surfaces"]
