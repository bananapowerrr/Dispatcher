# -*- coding: utf-8 -*-
"""FC-45 Agent Behavior — single UX control over existing intelligence flags.

Does not own Runtime state. Maps UI preferences → config/feature defaults
without inventing a second FSM.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import yaml

AUTONOMY_OFF = "off"
AUTONOMY_SUGGEST = "suggest"
AUTONOMY_AUTO = "auto"

SUGGESTIONS_ALL = "all"
SUGGESTIONS_IMPORTANT = "important"
SUGGESTIONS_NONE = "none"

ARCH_ASK = "ask"
ARCH_AUTO = "auto"
ARCH_OFF = "off"

VERIFY_AUTO = "automatic"
VERIFY_ASK = "always_ask"

# Named UX profiles (defaults only — user can override fields anytime)
PROFILE_BEGINNER = "beginner"
PROFILE_DEVELOPER = "developer"
PROFILE_ADVANCED = "advanced"
PROFILE_AUTO = "auto"

PROFILE_PRESETS: dict[str, dict[str, str]] = {
    PROFILE_BEGINNER: {
        "autonomy": AUTONOMY_AUTO,
        "suggestions": SUGGESTIONS_ALL,
        "architecture": ARCH_AUTO,
        "verification": VERIFY_AUTO,
    },
    PROFILE_DEVELOPER: {
        "autonomy": AUTONOMY_AUTO,
        "suggestions": SUGGESTIONS_IMPORTANT,
        "architecture": ARCH_ASK,
        "verification": VERIFY_AUTO,
    },
    PROFILE_ADVANCED: {
        "autonomy": AUTONOMY_SUGGEST,
        "suggestions": SUGGESTIONS_IMPORTANT,
        "architecture": ARCH_ASK,
        "verification": VERIFY_ASK,
    },
    PROFILE_AUTO: {
        "autonomy": AUTONOMY_AUTO,
        "suggestions": SUGGESTIONS_IMPORTANT,
        "architecture": ARCH_ASK,
        "verification": VERIFY_AUTO,
    },
}



@dataclass
class AgentBehavior:
    profile: str = PROFILE_AUTO
    autonomy: str = AUTONOMY_AUTO
    suggestions: str = SUGGESTIONS_IMPORTANT
    architecture: str = ARCH_ASK
    verification: str = VERIFY_AUTO

    def to_dict(self) -> dict[str, str]:
        return asdict(self)

    def normalize(self) -> "AgentBehavior":
        if self.autonomy not in (AUTONOMY_OFF, AUTONOMY_SUGGEST, AUTONOMY_AUTO):
            self.autonomy = AUTONOMY_AUTO
        if self.suggestions not in (SUGGESTIONS_ALL, SUGGESTIONS_IMPORTANT, SUGGESTIONS_NONE):
            self.suggestions = SUGGESTIONS_IMPORTANT
        if self.architecture not in (ARCH_ASK, ARCH_AUTO, ARCH_OFF):
            self.architecture = ARCH_ASK
        if self.verification not in (VERIFY_AUTO, VERIFY_ASK):
            self.verification = VERIFY_AUTO
        if self.profile not in PROFILE_PRESETS:
            self.profile = PROFILE_AUTO
        return self


def _ui_yaml_path(root: Path | None = None) -> Path:
    if root is None:
        root = Path(__file__).resolve().parents[2]
    return root / "config" / "ui.yaml"


def load_agent_behavior(root: Path | None = None) -> AgentBehavior:
    path = _ui_yaml_path(root)
    data: dict[str, Any] = {}
    if path.is_file():
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            if isinstance(raw, dict):
                data = raw.get("agent") or {}
        except Exception:
            data = {}
    if not isinstance(data, dict):
        data = {}
    b = AgentBehavior(
        profile=str(data.get("profile") or PROFILE_AUTO),
        autonomy=str(data.get("autonomy") or AUTONOMY_AUTO),
        suggestions=str(data.get("suggestions") or SUGGESTIONS_IMPORTANT),
        architecture=str(data.get("architecture") or ARCH_ASK),
        verification=str(data.get("verification") or VERIFY_AUTO),
    )
    return b.normalize()


def save_agent_behavior(behavior: AgentBehavior, root: Path | None = None) -> Path:
    path = _ui_yaml_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    cfg: dict[str, Any] = {}
    if path.is_file():
        try:
            cfg = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except Exception:
            cfg = {}
    if not isinstance(cfg, dict):
        cfg = {}
    cfg["agent"] = behavior.normalize().to_dict()
    path.write_text(
        yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return path


def behavior_summary(b: AgentBehavior | None = None) -> str:
    """One-line label for toolbar, e.g. 'Agent · Auto'."""
    b = (b or effective_behavior()).normalize()
    labels = {
        AUTONOMY_OFF: "Off",
        AUTONOMY_SUGGEST: "Suggest",
        AUTONOMY_AUTO: "Auto",
    }
    return f"Agent · {labels.get(b.autonomy, b.autonomy)}"


def apply_behavior_to_policy_hints(b: AgentBehavior) -> dict[str, Any]:
    """Hints for intelligence/runtime (soft) — does not force feature flags."""
    b = b.normalize()
    return {
        "autopilot_enabled": b.autonomy == AUTONOMY_AUTO,
        "suggest_only": b.autonomy == AUTONOMY_SUGGEST,
        "block_auto": b.autonomy == AUTONOMY_OFF,
        "suggestions_level": b.suggestions,
        "architecture_mode": b.architecture,
        "verify_always_ask": b.verification == VERIFY_ASK,
    }


def apply_profile(profile_id: str, root: Path | None = None) -> AgentBehavior:
    """Apply named profile defaults and persist."""
    pid = (profile_id or PROFILE_AUTO).lower().strip()
    preset = PROFILE_PRESETS.get(pid) or PROFILE_PRESETS[PROFILE_AUTO]
    b = AgentBehavior(
        profile=pid if pid in PROFILE_PRESETS else PROFILE_AUTO,
        autonomy=preset["autonomy"],
        suggestions=preset["suggestions"],
        architecture=preset["architecture"],
        verification=preset["verification"],
    ).normalize()
    save_agent_behavior(b, root=root)
    return b


def list_profiles() -> list[dict[str, str]]:
    return [
        {"id": PROFILE_BEGINNER, "label": "Новичок", "hint": "Больше подсказок, безопасные решения сам"},
        {"id": PROFILE_DEVELOPER, "label": "Разработчик", "hint": "Спрашивает при архитектуре"},
        {"id": PROFILE_ADVANCED, "label": "Продвинутый", "hint": "Максимум контроля и trade-off"},
        {"id": PROFILE_AUTO, "label": "Авто", "hint": "Сам выбирает уровень вмешательства"},
    ]


# Session-level override (not persisted until save_agent_behavior)
_SESSION_OVERRIDE: AgentBehavior | None = None


def set_session_override(behavior: AgentBehavior | None) -> None:
    """Temporary override for current UI session; None clears."""
    global _SESSION_OVERRIDE
    _SESSION_OVERRIDE = behavior.normalize() if behavior is not None else None


def clear_session_override() -> None:
    set_session_override(None)


def effective_behavior(root: Path | None = None) -> AgentBehavior:
    """Session override wins over ui.yaml profile."""
    if _SESSION_OVERRIDE is not None:
        return _SESSION_OVERRIDE
    return load_agent_behavior(root)

