# -*- coding: utf-8 -*-
"""Offline tests for config_schema validators."""
from __future__ import annotations

from core.config_schema import (
    validate_feature_flags,
    validate_providers,
    validate_workers,
)


def test_workers_ok():
    data = [
        {
            "name": "aider_local",
            "harness": "aider",
            "provider": "ollama",
            "timeout": 300,
            "tier": 5,
            "complexity": 2,
        }
    ]
    rep = validate_workers(data)
    assert rep.ok
    assert not any(i.level == "error" for i in rep.issues)


def test_workers_duplicate_name():
    data = [
        {"name": "a", "harness": "aider", "provider": "ollama"},
        {"name": "a", "harness": "aider", "provider": "ollama"},
    ]
    rep = validate_workers(data)
    assert not rep.ok
    assert any("duplicate" in i.message for i in rep.issues)


def test_workers_not_list():
    rep = validate_workers({"name": "x"})
    assert not rep.ok


def test_providers_ok():
    data = [
        {"id": "ollama", "type": "ollama", "models": ["qwen2.5-coder:7b"]},
        {"id": "lmstudio", "type": "openai_compatible", "models": []},
    ]
    rep = validate_providers(data)
    assert rep.ok


def test_providers_duplicate_id():
    data = [{"id": "x", "type": "ollama"}, {"id": "x", "type": "ollama"}]
    rep = validate_providers(data)
    assert not rep.ok


def test_feature_flags_bool():
    rep = validate_feature_flags({"features": {"skills": True, "autopilot": False}})
    assert rep.ok


def test_feature_flags_bad_root():
    rep = validate_feature_flags([1, 2, 3])
    assert not rep.ok
