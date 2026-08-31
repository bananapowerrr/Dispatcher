# -*- coding: utf-8 -*-
"""Тесты adaptive ranker: профили, обучение по корзинам сложности, причины
недоступности, ограничение bias. Без сети и CLI."""
from __future__ import annotations
import time

from health import HealthRegistry
from ranking import (AdaptiveRanker, ExecutorProfile, OutcomeStats, _bucket,
                     make_key)
from workers import Worker
from providers.registry import Provider


def test_bucket_mapping():
    assert _bucket(1) == "low"
    assert _bucket(2) == "low"
    assert _bucket(3) == "med"
    assert _bucket(4) == "high"
    assert _bucket(5) == "high"


def test_make_key():
    assert make_key("aider", "ollama", "qwen2.5-coder:7b") == "aider:ollama:qwen2.5-coder:7b"
    assert make_key("cli", "local", "") == "cli:local"


def test_profile_record_and_stats(tmp_path):
    prof = ExecutorProfile(key="k", executor="aider", provider="ollama")
    prof.record(True, latency=5.0, complexity=3)
    prof.record(False, latency=0.0, complexity=3)
    prof.record(True, latency=5.0, complexity=4)   # другая корзина
    assert prof.usage == 3
    med = prof.stats(3)
    assert med.total == 2 and med.success == 1
    high = prof.stats(4)
    assert high.total == 1 and med.success_rate == 0.5


def test_adaptive_score_smoke():
    prof = ExecutorProfile(key="k")
    for _ in range(10):
        prof.record(True, latency=3.0, complexity=3)
    assert prof.adaptive_score(3, base_score=1.0) > 1.0  # успешный -> бонус
    prof2 = ExecutorProfile(key="k2")
    for _ in range(10):
        prof2.record(False, latency=3.0, complexity=3)
    assert prof2.adaptive_score(3, base_score=1.0) < 1.0  # провальный -> штраф


def test_adaptive_score_few_samples_no_bias():
    prof = ExecutorProfile(key="k")
    prof.record(True, latency=1.0, complexity=3)
    assert prof.adaptive_score(3, base_score=1.0) == 1.0  # <3 исходов — без поправки


def test_ranker_learn_persists(tmp_path):
    score_file = tmp_path / "ranker.json"
    r = AdaptiveRanker(score_file)
    r.learn("aider", "ollama", "qwen2.5-coder:7b", ok=True, latency=4.0, complexity=3)
    r.learn("aider", "ollama", "qwen2.5-coder:7b", ok=False, latency=0.0, complexity=3)
    assert score_file.is_file()
    r2 = AdaptiveRanker(score_file)
    prof = r2.profiles.get("aider:ollama:qwen2.5-coder:7b")
    assert prof is not None
    assert prof.usage == 2
    assert prof.stats(3).success == 1 and prof.stats(3).fail == 1


def test_ranker_learn_successful_bias_positive(tmp_path):
    r = AdaptiveRanker(tmp_path / "r.json")
    for _ in range(4):
        r.learn("aider", "ollama", "m", ok=True, latency=3.0, complexity=3)
    biased = r.apply_bias(10.0, "aider", "ollama", "m", complexity=3, base_score=1.0)
    assert biased > 10.0


def test_ranker_reasons_unavailable_workflow(tmp_path):
    h = HealthRegistry(state_file=tmp_path / "h.json")
    worker = Worker(name="w1", command=("{aider}", "{message}"), harness="aider",
                    provider="ollama", model="qwen2.5-coder:7b", complexity=2)
    h.register("w1", 1)
    h.begin_task("w1")   # слот занят
    r = AdaptiveRanker(tmp_path / "r.json")
    reasons = r.reasons([worker], h, None)
    row = reasons[0]
    assert row["accessible"] is False
    assert "слоты заняты" in row["reason"]
    h.end_task("w1")
    reasons = r.reasons([worker], h, None)
    assert reasons[0]["accessible"] is True


def test_ranker_reasons_rate_limit(tmp_path):
    h = HealthRegistry(state_file=tmp_path / "h.json")
    worker = Worker(name="w1", command=("{aider}", "{message}"), harness="aider",
                    provider="ollama", model="m", complexity=3)
    h.register("w1", 1)
    h.failure("w1", "429 rate limit", timed_out=False)
    r = AdaptiveRanker(tmp_path / "r.json")
    row = r.reasons([worker], h, None)[0]
    assert row["accessible"] is False
    assert "rate-limit" in row["reason"].lower() or "cooldown" in row["reason"].lower()


def test_ranker_register_worker_from_provider(tmp_path):
    p = Provider({"id": "ollama", "type": "ollama", "billing": "local",
                  "models": ["qwen2.5-coder:7b"], "capabilities": ["coding", "tools"]})
    w = Worker(name="w", command=("{aider}", "{message}"), harness="cli",
               provider="ollama", model="qwen2.5-coder:7b", complexity=2)
    r = AdaptiveRanker(tmp_path / "r.json")
    r.register_worker(w)
    key = make_key(w.harness, w.provider, w.model)
    assert key in r.profiles
    assert r.profiles[key].capabilities is not None
