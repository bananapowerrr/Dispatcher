# -*- coding: utf-8 -*-
from __future__ import annotations

from types import SimpleNamespace


def test_load_profiles_has_local_and_cloud():
    from core.model_profiles import load_profiles

    profiles = load_profiles(force=True)
    assert "local_qwen_7b" in profiles
    assert profiles["local_qwen_7b"].rag_strictness == "high"
    assert profiles["local_qwen_7b"].context_total_chars() <= 24_000


def test_profile_for_worker_local():
    from core.model_profiles import profile_for_worker

    w = SimpleNamespace(
        name="aider_local",
        provider="ollama",
        tier=5,
        profile="",
        backend="",
    )
    p = profile_for_worker(w)
    assert p.backend in ("aider_cli", "aider")
    assert p.rag_strictness == "high"


def test_profile_for_worker_cloud_native():
    from core.model_profiles import profile_for_worker

    w = SimpleNamespace(
        name="aider_openrouter",
        provider="openrouter",
        tier=9,
        profile="",
        backend="",
    )
    p = profile_for_worker(w)
    assert p.context_window >= 32000 or p.rag_strictness in ("low", "medium")


def test_adapt_protocol_follows_backend():
    from core.tool_registry import adapt_for_worker

    local = SimpleNamespace(
        name="aider_local", harness="aider", provider="ollama",
        backend="aider_cli", profile="local_qwen_7b",
    )
    cloud = SimpleNamespace(
        name="or", harness="cli", provider="openrouter",
        backend="native_tools", profile="cloud_openrouter",
    )
    a = adapt_for_worker(local)
    b = adapt_for_worker(cloud)
    assert a["protocol"] == "text"
    assert b["protocol"] == "openai"
    assert b.get("tools_openai") is not None


def test_budget_for_profile_scales():
    from intelligence.context_budget import budget_for_profile

    tight = budget_for_profile("local_qwen_7b")
    wide = budget_for_profile("cloud_openrouter")
    assert tight.total_chars <= wide.total_chars


def test_native_backend_flag():
    from core.native_backend import native_backend_enabled

    w = SimpleNamespace(backend="native_tools", name="x", provider="openrouter", tier=9, profile="")
    assert native_backend_enabled(w) is True
