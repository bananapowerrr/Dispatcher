# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path


def test_plugin_registry_load_disabled(monkeypatch):
    from core import feature_flags as ff
    from core import plugin_registry as pr

    ff.set_flag("conversation", False)
    pr.clear_cache()
    assert pr.load("conversation") is None
    assert pr._ERRORS.get("conversation") == "disabled"


def test_plugin_registry_load_verify_policy():
    from core import feature_flags as ff
    from core import plugin_registry as pr

    ff.set_flag("verify_policy", True)
    pr.clear_cache()
    mod = pr.load("verify_policy")
    assert mod is not None
    assert hasattr(mod, "apply_verify_policy")


def test_soft_call_default():
    from core.plugin_registry import soft_call, clear_cache
    clear_cache()
    assert soft_call("no_such_plugin", "foo", default=42) == 42


def test_list_presets_and_apply(tmp_path, monkeypatch):
    from core import feature_flags as ff

    # use project presets file
    presets = ff.list_presets()
    names = {p["name"] for p in presets}
    assert "minimal" in names
    assert "balanced" in names
    assert "night_autonomous" in names

    path = tmp_path / "feature_flags.yaml"
    path.write_text("features:\n  conversation: true\n", encoding="utf-8")
    monkeypatch.setenv("AGENTBUS_FEATURE_FLAGS", str(path))
    ff.reload_flags()
    flags = ff.apply_preset("minimal", save=True)
    assert flags.get("autopilot") is False
    assert flags.get("verify_policy") is True
    assert flags.get("skills") is True
    text = path.read_text(encoding="utf-8")
    assert "autopilot: false" in text

    flags2 = ff.apply_preset("night_autonomous", save=True)
    assert flags2.get("autopilot") is True
    assert flags2.get("night_scheduler") is True
