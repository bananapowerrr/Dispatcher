# -*- coding: utf-8 -*-
"""FC-36E/F Configuration Advisor tests."""
from __future__ import annotations

from core.capability_scan import CapabilityReport, HardwareInfo, ModelInfo
from core.configuration_advisor import (
    advise_configuration,
    first_run_summary,
    match_roles,
)


def test_match_roles_prefers_coder_for_code():
    models = [
        ModelInfo(id="a", provider="ollama", name="qwen2.5:1.5b-instruct", roles=["meta", "chat"], source="live"),
        ModelInfo(id="b", provider="ollama", name="qwen2.5-coder:7b", roles=["code"], source="live"),
    ]
    asn = match_roles(models)
    by = {a.role: a for a in asn}
    assert by["code"].model_name == "qwen2.5-coder:7b"
    assert by["meta"].model_name == "qwen2.5:1.5b-instruct"


def test_match_roles_empty_fallback():
    asn = match_roles([])
    assert all(a.fallback or a.reason for a in asn)


def test_advise_core_only():
    rep = CapabilityReport(
        hardware=HardwareInfo(ram_gb=4, os="Linux"),
        models=[],
        providers_reachable={},
        recommended_mode="core_only",
        recommendations=["use skills"],
    )
    adv = advise_configuration(rep)
    assert adv.mode == "core_only"
    assert adv.steps
    text = adv.format_human()
    assert "Configuration" in text


def test_advise_local_assignments():
    models = [
        ModelInfo(id="1", provider="ollama", name="qwen2.5-coder:7b", roles=["code"], source="live", available=True),
        ModelInfo(id="2", provider="ollama", name="qwen2.5:1.5b", roles=["meta"], source="live", available=True),
    ]
    rep = CapabilityReport(
        hardware=HardwareInfo(ram_gb=16, vram_gb=8, has_gpu_hint=True),
        models=models,
        providers_reachable={"ollama": True},
        recommended_mode="local",
    )
    adv = advise_configuration(rep)
    assert adv.env_hints.get("AGENTBUS_WORKER_MODEL")
    assert any(a.role == "code" and a.model_name for a in adv.assignments)


def test_first_run_summary_offline():
    s = first_run_summary(probe_network=False)
    assert "Mode" in s or "mode" in s.lower() or "Configuration" in s
