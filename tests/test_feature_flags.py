# -*- coding: utf-8 -*-
import os
from pathlib import Path


def _clear_feature_env(monkeypatch):
    monkeypatch.delenv("AGENTBUS_FEATURE_FLAGS", raising=False)
    for k in list(os.environ):
        if k.startswith("AGENTBUS_FEATURE_"):
            monkeypatch.delenv(k, raising=False)


def test_defaults_enabled(monkeypatch, tmp_path):
    """With empty flags file and no env → KNOWN defaults (True)."""
    _clear_feature_env(monkeypatch)
    cfg = tmp_path / "empty_flags.yaml"
    cfg.write_text("features: {}\n", encoding="utf-8")
    monkeypatch.setenv("AGENTBUS_FEATURE_FLAGS", str(cfg))
    import core.feature_flags as ff
    ff.reload_flags()
    assert ff.is_enabled("conversation") is True
    assert ff.is_enabled("skills") is True


def test_env_override(monkeypatch, tmp_path):
    _clear_feature_env(monkeypatch)
    cfg = tmp_path / "empty_flags.yaml"
    cfg.write_text("features: {}\n", encoding="utf-8")
    monkeypatch.setenv("AGENTBUS_FEATURE_FLAGS", str(cfg))
    monkeypatch.setenv("AGENTBUS_FEATURE_CONVERSATION", "0")
    import core.feature_flags as ff
    ff.reload_flags()
    assert ff.is_enabled("conversation") is False
    monkeypatch.setenv("AGENTBUS_FEATURE_CONVERSATION", "1")
    ff.reload_flags()
    assert ff.is_enabled("conversation") is True


def test_yaml_disable(monkeypatch, tmp_path):
    cfg = tmp_path / "flags.yaml"
    cfg.write_text(
        "features:\n  autopilot: false\n  skills: true\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("AGENTBUS_FEATURE_FLAGS", str(cfg))
    for k in list(os.environ):
        if k.startswith("AGENTBUS_FEATURE_") and k != "AGENTBUS_FEATURE_FLAGS":
            monkeypatch.delenv(k, raising=False)
    import core.feature_flags as ff
    ff.reload_flags()
    assert ff.is_enabled("autopilot") is False
    assert ff.is_enabled("skills") is True
    snap = ff.snapshot()
    assert "autopilot" in snap["disabled"]


def test_optional_import_respects_flag(monkeypatch, tmp_path):
    cfg = tmp_path / "empty_flags.yaml"
    cfg.write_text("features: {}\n", encoding="utf-8")
    monkeypatch.setenv("AGENTBUS_FEATURE_FLAGS", str(cfg))
    monkeypatch.setenv("AGENTBUS_FEATURE_SKILLS", "0")
    for k in list(os.environ):
        if k.startswith("AGENTBUS_FEATURE_") and k not in (
            "AGENTBUS_FEATURE_FLAGS",
            "AGENTBUS_FEATURE_SKILLS",
        ):
            monkeypatch.delenv(k, raising=False)
    import core.feature_flags as ff
    ff.reload_flags()
    assert ff.optional_import("skills", feature="skills") is None


def test_project_yaml_conversation_is_bool():
    import core.feature_flags as ff
    val = ff.is_enabled("conversation")
    assert isinstance(val, bool)
