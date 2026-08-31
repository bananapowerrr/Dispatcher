# -*- coding: utf-8 -*-
"""Тесты dynamic pool: построение воркеров из usable free/local провайдеров,
дедупликация, free-only guard, события. Без сети и CLI."""
from __future__ import annotations

from dynamicpool import (build_dynamic_workers, emit_pool_event, is_foreign_provider,
                         _wm_key)
from providers.registry import Provider
from workers import Worker


def _provider(**kw):
    base = {"id": "p", "type": "openai_compatible", "billing": "free",
            "enabled": True, "dynamic": False}
    base.update(kw)
    return Provider(base)


def test_empty_when_no_usable_providers():
    # paid + ALLOW_PAID=false -> не usable -> пусто
    p = _provider(id="paid", billing="paid", enabled=True)
    assert build_dynamic_workers([p], []) == []


def test_disabled_provider_not_built():
    p = _provider(id="kilo", enabled=False, dynamic=True)
    assert build_dynamic_workers([p], []) == []


def test_dynamic_auto_worker_built():
    p = _provider(id="kilo", enabled=True, dynamic=True, priority=55)
    ws = build_dynamic_workers([p], [])
    assert len(ws) == 1
    w = ws[0]
    assert w.provider == "kilo" and w.model == "auto"
    assert w.name == "kilo_auto"
    assert is_foreign_provider(w) is True


def test_regular_provider_one_worker_per_model():
    p = _provider(id="groq", enabled=True, models=["qwen-27b", "gpt-oss"])
    ws = build_dynamic_workers([p], [])
    assert {w.model for w in ws} == {"qwen-27b", "gpt-oss"}
    assert all(w.provider == "groq" for w in ws)


def test_deduplicates_against_existing():
    p = _provider(id="groq", enabled=True, models=["qwen-27b"])
    existing = [Worker(name="groq_qwen", command=("{aider}", "{message}"),
                       harness="aider", provider="groq", model="qwen-27b",
                       complexity=3, enabled=True)]
    ws = build_dynamic_workers([p], existing)
    assert ws == []  # уже есть такой worker -> не дублируем


def test_dynamic_dedup_auto():
    p = _provider(id="kilo", enabled=True, dynamic=True)
    existing = [Worker(name="kilo_auto", command=("{aider}", "{message}"),
                       harness="aider", provider="kilo", model="auto",
                       complexity=3, enabled=True)]
    assert build_dynamic_workers([p], existing) == []


def test_complexity_from_priority():
    assert _wm_key is not None  # smoke
    low = _provider(id="a", enabled=True, priority=50, models=["m"])
    high = _provider(id="b", enabled=True, priority=90, models=["m"])
    wlow = build_dynamic_workers([low], [])[0]
    whigh = build_dynamic_workers([high], [])[0]
    assert wlow.complexity < whigh.complexity


def test_emit_pool_event_never_throws():
    # сбрасываем глобальный BUS (чтобы не копить в синглтоне)
    from eventbus import reset_bus as rb
    rb()
    bull = [Provider({"id": "kilo", "type": "openai_compatible", "billing": "free",
                      "enabled": True, "dynamic": True})]
    ws = build_dynamic_workers(bull, [])
    # не должно бросать при любом состоянии пула
    emit_pool_event(ws)
    emit_pool_event([])


def test_ollama_provider_not_foreign():
    p = _provider(id="ollama", type="ollama", billing="local", enabled=True,
                  models=["qwen2.5-coder:7b"])
    ws = build_dynamic_workers([p], [])
    assert ws and ws[0].provider == "ollama"
    assert is_foreign_provider(ws[0]) is False
