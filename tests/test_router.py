# -*- coding: utf-8 -*-
"""Тесты router: provider-cooldown-aware выбор воркера (v3 P3).

select_executor с capacity исключает воркеров чьего provider:model в cooldown;
обратно совместим — без capacity работает как раньше.
"""
from __future__ import annotations
import time

import pytest

from health import HealthRegistry
from router import select_executor, task_complexity
from workers import Worker


@pytest.fixture
def health(tmp_path):
    return HealthRegistry(state_file=tmp_path / "ws.json")


def _w(name, provider="ollama", model="m", complexity=2, quality=1.0, caps=()):
    return Worker(name=name, command=("{aider}", "{message}"), harness="aider",
                  provider=provider, model=model, complexity=complexity,
                  quality=quality, enabled=True, capabilities=tuple(caps))


class _FakeCap:
    def __init__(self, blocked_keys, factors=None):
        self.blocked = set(blocked_keys)
        self.factors = factors or {}

    def available(self, key: str) -> bool:
        return key not in self.blocked

    def quota_factor(self, key: str) -> float:
        return self.factors.get(key, 1.0)  # default 1.0 (нет ограничений)


def test_without_capacity_matches_before(health):
    health.register("w1")
    w = _w("w1", provider="ollama", model="whatev")
    assert select_executor([w], health, {"message": "hi"}) is w


def test_cooldown_provider_worker_skipped(health):
    for n in ("a", "b"):
        health.register(n)
    a = _w("a", provider="ollama", model="local-m", complexity=2)
    b = _w("b", provider="groq", model="qq", complexity=4)
    cap = _FakeCap({"groq:qq"})
    # задача простая — здоровый локальный a выигрывает, groq в cooldown пропущен
    assert select_executor([a, b], health, {"message": "x" * 100}, capacity=cap) is a


def test_local_worker_not_penalized_when_key_unknown(health):
    health.register("w1")
    w = _w("w1", provider="local", model="", complexity=2)
    cap = _FakeCap(set())  # нет ключа local:auto -> UNKNOWN -> доступен
    assert select_executor([w], health, {"message": "hi"}, capacity=cap) is w


def test_capacity_none_and_exception_safe(health):
    health.register("w1")
    w = _w("w1", provider="ollama", model="m")
    class _Boom:
        def available(self, key):
            raise RuntimeError("boom")
    assert select_executor([w], health, {"message": "hi"}, capacity=_Boom()) is w


def test_all_cooldown_returns_none(health):
    health.register("b")
    b = _w("b", provider="groq", model="qq")
    cap = _FakeCap({"groq:qq"})
    assert select_executor([b], health, {"message": "hi"}, capacity=cap) is None


def test_task_complexity_heuristic():
    assert task_complexity({"message": "архитектура сервиса", "files": ["a", "b"]}) == 4
    assert task_complexity({"message": "add docs", "files": ["a.py"]}) == 2
    assert task_complexity({"metadata": {"complexity": 5}}) == 5


# ---------- capabilities-aware выбор (v3) ----------
def test_required_cap_filters_workers(health):
    for n in ("t", "b"):
        health.register(n)
    t = _w("t", provider="groq", model="qq", caps=["tools"])
    b = _w("b", provider="groq", model="v", caps=["coding"])
    assert select_executor([t, b], health, {"message": "hi"}, required_cap="tools") is t
    assert select_executor([t, b], health, {"message": "hi"}, required_cap="coding") is b


def test_required_cap_treats_empty_caps_as_capable(health):
    health.register("plain")
    plain = _w("plain", provider="ollama", model="m", caps=())  # без declared -> able
    assert select_executor([plain], health, {"message": "hi"}, required_cap="streaming") is plain


def test_required_cap_no_match_returns_none(health):
    health.register("b")
    b = _w("b", provider="groq", model="qq", caps=["coding"])
    assert select_executor([b], health, {"message": "hi"}, required_cap="tools") is None


# ---------- soft-quota (v3): rationed провайдер деприоритизируется, не выкинут ----------
def test_exhausted_soft_quota_deprioritized_over_full(health):
    for n in ("local_full", "cloud_ration"):
        health.register(n)
    local = _w("local_full", provider="ollama", model="lm", complexity=2, quality=1.0)
    cloud = _w("cloud_ration", provider="groq", model="qq", complexity=4, quality=1.0)
    # cloud с нулевой квотой, local в норме -> выбираем local
    cap = _FakeCap(set(), factors={"groq:qq": 0.0})
    assert select_executor([cloud, local], health, {"message": "x" * 200}, capacity=cap) is local


def test_rationed_only_still_selectable_as_fallback(health):
    health.register("only")
    w = _w("only", provider="groq", model="qq", complexity=3)
    cap = _FakeCap(set(), factors={"groq:qq": 0.0})
    # единственный воркер, хоть и rationed (мягкая квота не блокирует) -> выбираем
    assert select_executor([w], health, {"message": "hi"}, capacity=cap) is w


def test_soft_quota_factor_zero_default_available(health):
    # default capacity без настройки квоты = factor 1.0
    health.register("w1")
    w = _w("w1", provider="ollama", model="m")
    assert select_executor([w], health, {"message": "hi"}, capacity=_FakeCap(set())) is w
