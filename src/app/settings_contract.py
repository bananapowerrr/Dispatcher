# -*- coding: utf-8 -*-
"""Day-13: settings surface contract (read-only vs editable).

Does not change runtime / FSM / intake. Documents which SettingsPanel
tabs may mutate yaml on disk vs pure view. Used by tests and future UI guards.
"""
from __future__ import annotations

from typing import Any

# Tabs that may write config/*.yaml when user clicks Save.
EDITABLE_TABS: frozenset[str] = frozenset(
    {
        "workers",  # workers.yaml enabled + priority
        "language",  # ui language preference
        "ui",  # layout / theme prefs (layout_prefs)
        "agent",  # agent_behavior profile
    }
)

# Tabs that only display yaml / status (no Save that mutates core policy).
READ_ONLY_TABS: frozenset[str] = frozenset(
    {
        "providers",  # providers.yaml view
        "context",  # context budget / models view
        "prompt",  # prompt templates view
        "policy",  # policy.yaml view
        "flags",  # feature_flags.yaml view
        "presets",  # feature_presets view/apply (apply is explicit, not silent)
    }
)

ALL_TABS: frozenset[str] = EDITABLE_TABS | READ_ONLY_TABS


def is_editable_tab(tab: str) -> bool:
    """True if Settings tab is allowed to persist changes."""
    key = (tab or "").strip().lower()
    # normalize common RU/EN labels → keys
    aliases = {
        "воркеры": "workers",
        "workers": "workers",
        "язык": "language",
        "language": "language",
        "интерфейс": "ui",
        "ui": "ui",
        "agent": "agent",
        "провайдеры": "providers",
        "providers": "providers",
        "контекст": "context",
        "context": "context",
        "промпт": "prompt",
        "prompt": "prompt",
        "политика": "policy",
        "policy": "policy",
        "флаги": "flags",
        "flags": "flags",
        "пресеты": "presets",
        "presets": "presets",
    }
    key = aliases.get(key, key)
    return key in EDITABLE_TABS


def is_read_only_tab(tab: str) -> bool:
    return not is_editable_tab(tab)


def settings_contract_summary() -> dict[str, Any]:
    """Machine-readable contract for acceptance matrix / doctor."""
    return {
        "editable": sorted(EDITABLE_TABS),
        "read_only": sorted(READ_ONLY_TABS),
        "note": "Offline freeze: no silent writes to policy/providers/flags.",
    }
