# -*- coding: utf-8 -*-
"""P0: ProviderRegistry / Free-only guard / reset_parser / capacity manager.

Проверяем декларативный реестр, разделение provider vs worker, cooldown
per provider:model и распознавание 429/Retry-After/человеческого текста.
"""
from __future__ import annotations
import json

import pytest

from providers.registry import Provider, load_providers
from providers.state import ProviderRegistry, key_for
from providers.reset import parse_retry_after, is_rate_limit
from providers.capacity import FreeCapacityManager


@pytest.fixture
def state(tmp_path):
    return ProviderRegistry(state_file=tmp_path / "ps.json")


# ---------- декларативный реестр ----------
def test_load_providers_returns_usable_gate():
    ps = load_providers()
    ids = {p.id for p in ps}
    assert "ollama" in ids          # локальный всегда в реестре
    assert "kilo" in ids
    assert "openrouter" in ids
    assert "groq" in ids
    assert "gemini" in ids


def test_free_only_guard_blocks_paid():
    # ALLOW_PAID=false в тестовом окружении (config не задаёт его) -> paid блокируется
    p = Provider({"id": "x", "type": "openai_compatible", "billing": "paid",
                  "enabled": True, "base_url": "https://x"})
    assert p.is_usable() is False


def test_free_and_local_usable_by_default():
    p = Provider({"id": "o", "type": "ollama", "billing": "local", "enabled": True})
    assert p.is_usable() is True
    f = Provider({"id": "g", "type": "openai_compatible", "billing": "free",
                  "enabled": True})
    assert f.is_usable() is True


def test_env_gate_disables_provider():
    import os
    os.environ["AGENTBUS_TEST_GATE"] = "0"
    try:
        p = Provider({"id": "g", "type": "openai_compatible", "billing": "free",
                      "enabled": True, "enabled_env": "AGENTBUS_TEST_GATE"})
        assert p.is_usable() is False
    finally:
        os.environ.pop("AGENTBUS_TEST_GATE", None)


def test_dynamic_provider_key_is_auto():
    p = Provider({"id": "kilo", "type": "openai_compatible", "billing": "free",
                  "dynamic": True, "models": ["kilo-auto/free"]})
    assert p.model_keys() == ["kilo:auto"]


# ---------- state per provider:model ----------
def test_key_for():
    assert key_for("groq", "qwen") == "groq:qwen"
    assert key_for("ollama", "") == "ollama"


def test_provider_state_success_and_available(state):
    st = state.state("groq:m")
    assert st.available() is True
    state.success("groq:m", latency=1.0, provider="groq", model="m")
    assert state.state("groq:m").status == "AVAILABLE"
    assert state.state("groq:m").success_rate == 1.0


def test_provider_state_cooldown_blocks(state):
    state.failure("groq:m", "boom", status="ERROR", cooldown=30)
    assert not state.state("groq:m").available()


def test_provider_state_persist_restart(tmp_path):
    f = tmp_path / "ps.json"
    reg = ProviderRegistry(state_file=f)
    reg.failure("groq:m", "429", status="RATE_LIMITED", cooldown=10, provider="groq", model="m")
    reg.success("groq:m2", provider="groq", model="m2")
    reg2 = ProviderRegistry(state_file=f)
    assert reg2.state("groq:m").status == "RATE_LIMITED"
    assert reg2.state("groq:m2").success_count == 1
    # BUSY не переносится
    reg2.state("busy").status = "BUSY"
    reg2.save_state()
    reg3 = ProviderRegistry(state_file=f)
    assert reg3.state("busy").status == "AVAILABLE"


# ---------- reset parser ----------
def test_retry_after_numeric():
    secs, conf = parse_retry_after("Retry-After: 1837")
    assert secs == 1837.0 and conf > 0.9


def test_human_duration():
    secs, conf = parse_retry_after("Rate limit reached. Try again in 2h 17m")
    assert secs == 8220.0 and conf >= 0.8


def test_minutes_only():
    secs, _ = parse_retry_after("resets in 37m")
    assert secs == 2220.0


def test_seconds_only():
    secs, _ = parse_retry_after("try again in 45 sec")
    assert secs == 45.0


def test_plain_429_recognized_without_time():
    secs, conf = parse_retry_after("429")
    assert conf >= 0.5  # это rate-limit, но время неизвестно
    assert is_rate_limit("429")


def test_plain_numeric_retry_header():
    secs, _ = parse_retry_after("60")
    # голое число не распознаётся reset-parser'ом (нужен контекст) — capacity
    # обрабатывает Retry-After header отдельно.
    assert secs == 0.0


def test_reset_at_time():
    import datetime
    now = datetime.datetime.now()
    target = now + datetime.timedelta(hours=2)
    secs, conf = parse_retry_after(f"reset at {target.hour}:{target.minute:02d}")
    assert conf >= 0.6
    assert 1.5 * 3600 < secs < 2.5 * 3600


def test_irrelevant_text_not_rate_limit():
    assert not is_rate_limit("all good, processing fine")
    secs, conf = parse_retry_after("everything ok")
    assert secs == 0.0 and conf == 0.0


# ---------- capacity manager ----------
def test_deferred_quota_when_all_unavailable():
    ps = load_providers()
    cm = FreeCapacityManager(ps)
    # всё, кроме ollama, выключено; ollama доступна -> не deferred
    snap = cm.deferred_snapshot()
    assert snap["deferred"] is False


def test_cooldown_via_text_error(tmp_path):
    ps = load_providers()
    cm = FreeCapacityManager(ps, state=ProviderRegistry(state_file=tmp_path / "ps.json"))
    key = "groq:qwen/qwen3.8-27b"
    assert cm.available(key)
    r = cm.record_text_error(key, "HTTP 429 Rate limit reached. Try again in 37m",
                             "groq", "qwen/qwen3.8-27b")
    assert r["recognized"] is True
    assert r["cooldown"] == 2220.0
    assert not cm.available(key)
    assert any(c["key"] == key for c in cm.cooldown_list())


def test_cooldown_via_http_429_header(tmp_path):
    class Headers:
        def get(self, k):
            return "60" if k.lower() == "retry-after" else None
    ps = load_providers()
    cm = FreeCapacityManager(ps, state=ProviderRegistry(state_file=tmp_path / "ps.json"))
    r = cm.record_http_result("kilo:auto", ok=False, status=429, headers=Headers(),
                              provider="kilo")
    assert r["ok"] is False and r["status"] == "RATE_LIMITED"
    assert r["cooldown"] == 60.0
    assert not cm.available("kilo:auto")


def test_http_success_updates_quota(tmp_path):
    class Headers:
        def get(self, k):
            return {"x-ratelimit-remaining-requests": "817"}.get(k)
    ps = load_providers()
    cm = FreeCapacityManager(ps, state=ProviderRegistry(state_file=tmp_path / "ps.json"))
    r = cm.record_http_result("groq:m", ok=True, status=200, headers=Headers(),
                              latency=0.5, provider="groq", model="m")
    assert r["ok"] is True
    assert cm.state.state("groq:m").remaining_rpd == 817


# дымовой тест поставки: providers.yaml парсится без синтаксических ошибок
def test_yaml_registry_wellformed():
    from config import PROVIDERS_FILE
    from pathlib import Path
    p = Path(PROVIDERS_FILE)
    if p.is_file():
        raw = p.read_text(encoding="utf-8")
        assert "ollama" in raw
        assert "billing: local" in raw
        # декларативно — не хардкод guard'а в коде
        assert "AGENTBUS_PROVIDER_OLLAMA_ENABLED" in raw


# ---------- dynamic pool probe (без сети, через фейковый adapter) ----------
def test_probe_dynamic_fake_adapters(tmp_path):
    ps = load_providers()
    kilo = next((p for p in ps if p.id == "kilo"), None)
    if kilo is None:
        pytest.skip("kilo не в реестре")
    # явно включаем kilo для теста (не трогает глобальный env)
    kilo.enabled = True
    cm = FreeCapacityManager([kilo], state=ProviderRegistry(state_file=tmp_path / "ps.json"))

    class FakeAdapter:
        def probe(self, timeout=5.0):
            return (True, "ok")
    cm.adapters["kilo"] = FakeAdapter()

    pool = cm.probe_dynamic()
    row = next(r for r in pool if r["id"] == "kilo")
    assert row["ok"] is True and row["reason"] == "ok"


def test_probe_dynamic_skips_unusable(tmp_path):
    ps = load_providers()
    kilo = next((p for p in ps if p.id == "kilo"), None)
    if kilo is None:
        pytest.skip("kilo не в реестре")
    kilo.enabled = False           # по умолчанию выключен -> не пробируется
    cm = FreeCapacityManager([kilo], state=ProviderRegistry(state_file=tmp_path / "ps.json"))
    pool = cm.probe_dynamic()
    row = next(r for r in pool if r["id"] == "kilo")
    assert row["ok"] is False and row["reason"] == "not_usable"


def test_probe_dynamic_fake_adapter_down(tmp_path):
    ps = load_providers()
    groq = next((p for p in ps if p.id == "groq"), None)
    if groq is None:
        pytest.skip("groq не в реестре")
    groq.enabled = True
    cm = FreeCapacityManager([groq], state=ProviderRegistry(state_file=tmp_path / "ps.json"))

    class DownAdapter:
        def probe(self, timeout=5.0):
            return (False, "UNAVAILABLE_NETWORK")
    cm.adapters["groq"] = DownAdapter()

    pool = cm.probe_dynamic()
    row = next(r for r in pool if r["id"] == "groq")
    assert row["ok"] is False and row["reason"] == "UNAVAILABLE_NETWORK"


def test_probe_dynamic_swallows_adapter_exception(tmp_path):
    ps = load_providers()
    gemini = next((p for p in ps if p.id == "gemini"), None)
    if gemini is None:
        pytest.skip("gemini не в реестре")
    gemini.enabled = True
    cm = FreeCapacityManager([gemini], state=ProviderRegistry(state_file=tmp_path / "ps.json"))

    class BoomAdapter:
        def probe(self, timeout=5.0):
            raise RuntimeError("boom")
    cm.adapters["gemini"] = BoomAdapter()

    pool = cm.probe_dynamic()   # не должно бросать
    row = next(r for r in pool if r["id"] == "gemini")
    assert row["ok"] is False and "boom" in row["reason"]
