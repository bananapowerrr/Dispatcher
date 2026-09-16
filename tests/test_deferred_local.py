# -*- coding: utf-8 -*
"""Ollama (billing=local) никогда не провоцирует DEFERRED_QUOTA."""
from __future__ import annotations

from providers.capacity import FreeCapacityManager
from providers.registry import Provider


def _local_ollama() -> Provider:
    return Provider({
        "id": "ollama",
        "type": "ollama",
        "billing": "local",
        "enabled": True,
        "priority": 100,
        "models": ["qwen2.5-coder:7b"],
    })


def _free_cloud() -> Provider:
    # без api_key_env — is_usable() не требует ключ (удобно для unit-теста)
    return Provider({
        "id": "siliconflow",
        "type": "openai_compatible",
        "billing": "free",
        "enabled": True,
        "priority": 80,
        "dynamic": True,
        "models": ["deepseek-ai/DeepSeek-R1-Distill-Qwen-7B"],
    })


def test_local_never_deferred_even_if_cloud_down():
    """Все cloud в cooldown — Ollama всё равно available → deferred=False."""
    ollama = _local_ollama()
    cloud = _free_cloud()
    cap = FreeCapacityManager([ollama, cloud])
    for k in cloud.model_keys():
        cap.state.failure(k, "429 rate limit", status="RATE_LIMITED", cooldown=3600.0)
    snap = cap.deferred_snapshot()
    assert snap.get("deferred") is False
    assert "ollama" in snap.get("available", [])


def test_all_cloud_deferred_without_local():
    """Без local: все free в cooldown → deferred=True."""
    cloud = _free_cloud()
    cap = FreeCapacityManager([cloud])
    for k in cloud.model_keys():
        cap.state.failure(k, "429", status="RATE_LIMITED", cooldown=3600.0)
    snap = cap.deferred_snapshot()
    assert snap.get("deferred") is True
    assert "wake_at" in snap
