# -*- coding: utf-8 -*-
from pathlib import Path
from app.agent_behavior import (
    AgentBehavior,
    set_session_override,
    clear_session_override,
    effective_behavior,
    load_agent_behavior,
    apply_profile,
    AUTONOMY_OFF,
    PROFILE_DEVELOPER,
)

def test_session_override_wins(tmp_path: Path, monkeypatch):
    (tmp_path / "config").mkdir()
    monkeypatch.chdir(tmp_path)
    apply_profile(PROFILE_DEVELOPER, root=tmp_path)
    clear_session_override()
    base = load_agent_behavior(tmp_path)
    set_session_override(AgentBehavior(autonomy=AUTONOMY_OFF, profile="developer"))
    eff = effective_behavior(tmp_path)
    assert eff.autonomy == AUTONOMY_OFF
    clear_session_override()
    assert effective_behavior(tmp_path).autonomy == base.autonomy

def test_help_text_constant():
    import importlib.util
    path = Path("ui/help_dialog.py")
    src = path.read_text(encoding="utf-8")
    assert "ЦИКЛ РАБОТЫ" in src or "Agent" in src
    assert "?" in src
