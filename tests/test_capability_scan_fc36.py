# -*- coding: utf-8 -*-
"""FC-36A/B Capability Scan tests (offline)."""
from __future__ import annotations

from core.capability_scan import (
    HardwareInfo,
    ModelInfo,
    recommend_mode,
    scan_capabilities,
    scan_hardware,
    _infer_roles,
)


def test_scan_hardware():
    h = scan_hardware()
    assert h.os
    assert h.cpu_count >= 0
    assert h.ram_gb >= 0


def test_infer_roles():
    assert "code" in _infer_roles("qwen2.5-coder:7b")
    assert "meta" in _infer_roles("qwen2.5:1.5b-instruct")


def test_recommend_core_only():
    hw = HardwareInfo(ram_gb=4, cpu_count=2, os="Linux", arch="x86_64")
    mode, tips = recommend_mode(hw, [], {})
    assert mode == "core_only"
    assert tips


def test_recommend_local_with_models():
    hw = HardwareInfo(ram_gb=16, vram_gb=8, has_gpu_hint=True)
    models = [
        ModelInfo(id="1", provider="ollama", name="qwen2.5-coder:7b", roles=["code"], source="live"),
        ModelInfo(id="2", provider="ollama", name="qwen2.5:1.5b", roles=["meta"], source="live"),
    ]
    mode, _ = recommend_mode(hw, models, {"ollama": True})
    assert mode == "local"


def test_scan_offline_no_network():
    r = scan_capabilities(probe_network=False, include_config=True)
    assert r.duration_ms >= 0
    assert r.recommended_mode in ("core_only", "local", "hybrid", "cloud")
    text = r.format_human()
    assert "Capability" in text or "OS" in text
