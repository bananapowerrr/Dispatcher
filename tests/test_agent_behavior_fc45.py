# -*- coding: utf-8 -*-
from pathlib import Path

from app.agent_behavior import (
    AgentBehavior,
    apply_behavior_to_policy_hints,
    behavior_summary,
    load_agent_behavior,
    save_agent_behavior,
)


def test_defaults(tmp_path: Path):
    (tmp_path / "config").mkdir()
    b = load_agent_behavior(tmp_path)
    assert b.autonomy == "auto"
    assert "Auto" in behavior_summary(b)


def test_roundtrip(tmp_path: Path):
    (tmp_path / "config").mkdir()
    b = AgentBehavior(autonomy="suggest", architecture="off")
    save_agent_behavior(b, tmp_path)
    b2 = load_agent_behavior(tmp_path)
    assert b2.autonomy == "suggest"
    assert b2.architecture == "off"


def test_policy_hints():
    h = apply_behavior_to_policy_hints(AgentBehavior(autonomy="off"))
    assert h["block_auto"] is True
    assert h["autopilot_enabled"] is False
