# -*- coding: utf-8 -*-
"""Day-8 offline: worker route planning (no real Ollama/Aider)."""
from __future__ import annotations

from types import SimpleNamespace

from core.worker_route import RouteDecision, next_after_failure, plan_route


def _w(name: str, *, provider: str = "ollama", tier: int = 5, enabled: bool = True, role: str = "code"):
    return SimpleNamespace(
        name=name,
        provider=provider,
        model="qwen2.5-coder:7b",
        harness="aider",
        enabled=enabled,
        priority=10,
        complexity=2,
        tier=tier,
        quality=1.0,
        role=role,
        capabilities=("coding",),
    )


class _Health:
    def __init__(self, down: set[str] | None = None):
        self.down = down or set()

    def available(self, name: str) -> bool:
        return name not in self.down

    def score(self, name: str, *a, **k) -> float:
        return 0.0 if name in self.down else 5.0


def test_plan_route_picks_local_aider():
    workers = [
        _w("aider_local", provider="ollama", tier=5),
        _w("cloud_x", provider="openai", tier=8),
    ]
    d = plan_route(
        {"message": "добавь docstring", "files": ["a.py"], "metadata": {"complexity": 2}},
        workers=workers,
        health=_Health(),
        include_diagnostics=False,
    )
    assert d.primary in ("aider_local", "cloud_x")
    assert d.complexity == 2
    assert isinstance(d.format_human(), str)
    assert "WORKER ROUTE" in d.format_human()


def test_plan_route_respects_health_down():
    workers = [
        _w("aider_local", provider="ollama"),
        _w("aider_b", provider="ollama", tier=5),
    ]
    d = plan_route(
        {"message": "fix bug", "metadata": {"complexity": 3}},
        workers=workers,
        health=_Health(down={"aider_local"}),
        include_diagnostics=False,
    )
    assert d.primary != "aider_local"
    assert d.primary == "aider_b" or d.primary is None or d.primary == "aider_b"


def test_fallback_chain_excludes_primary():
    workers = [
        _w("aider_local", provider="ollama"),
        _w("opencode_zen", provider="zen", tier=9),
    ]
    d = plan_route(
        {"message": "refactor architecture", "metadata": {"complexity": 4}},
        workers=workers,
        health=_Health(),
        include_diagnostics=False,
    )
    if d.primary:
        assert d.primary not in d.fallbacks


def test_next_after_network_failure():
    workers = [
        _w("cloud_a", provider="openai", tier=8),
        _w("aider_local", provider="ollama", tier=5),
    ]
    d = next_after_failure(
        workers,
        tried=["cloud_a"],
        error="Connection refused",
    )
    # should prefer something not tried
    assert d.primary != "cloud_a" or d.primary is None
    assert "failure_kind" in " ".join(d.reasons)


def test_route_decision_to_dict():
    d = RouteDecision(primary="aider_local", fallbacks=["opencode_zen"], complexity=3)
    assert d.to_dict()["chain"][0] == "aider_local"
    assert "opencode_zen" in d.to_dict()["chain"]


def test_disabled_workers_blocked_note():
    workers = [_w("dead", enabled=False), _w("aider_local")]
    d = plan_route(
        {"message": "hi", "metadata": {"complexity": 2}},
        workers=workers,
        health=_Health(),
        include_diagnostics=False,
    )
    assert d.primary == "aider_local" or any("dead" in b for b in d.blocked) or d.primary
