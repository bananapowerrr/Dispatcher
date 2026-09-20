# -*- coding: utf-8 -*-
"""Day 13.1: SettingsPanel obeys settings_contract (RO tabs have no mutation path)."""
from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _panel_source() -> str:
    p = ROOT / "ui" / "settings_panel.py"
    if not p.is_file():
        # offline artifact path
        p = Path("/home/workdir/artifacts/settings_panel.py")
    return p.read_text(encoding="utf-8")


def test_contract_editable_tabs():
    from app.settings_contract import EDITABLE_TABS, READ_ONLY_TABS, is_editable_tab, is_read_only_tab

    assert "workers" in EDITABLE_TABS
    assert "language" in EDITABLE_TABS
    assert "ui" in EDITABLE_TABS
    assert "agent" in EDITABLE_TABS
    for t in ("providers", "context", "prompt", "policy", "flags", "presets"):
        assert t in READ_ONLY_TABS
        assert is_read_only_tab(t)
        assert not is_editable_tab(t)
    assert is_editable_tab("workers")
    assert is_editable_tab("Воркеры")


def test_ro_tabs_have_no_mutation_calls_in_source():
    """AST/source: RO builders must not call set_flag / set_active_policy / write_text for core policy."""
    src = _panel_source()
    # global ban for RO mutation APIs
    assert "set_flag(" not in src
    assert "set_active_policy(" not in src
    assert "_save_all_flags" not in src
    assert "Сохранить промпт" not in src
    assert "Применить пресет" not in src
    # editable retained
    assert "_save_workers" in src
    assert "set_agent_language" in src
    assert "apply_profile" in src
    assert "_ro_banner" in src


def test_ro_methods_call_banner():
    src = _panel_source()
    tree = ast.parse(src)
    ro_names = {
        "_build_providers_tab",
        "_build_context_tab",
        "_build_prompt_tab",
        "_build_policy_tab",
        "_build_flags_tab",
        "_build_presets_tab",
    }
    found = {}
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "SettingsPanel":
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name in ro_names:
                    body_src = ast.get_source_segment(src, item) or ""
                    found[item.name] = "_ro_banner" in body_src
    for name in ro_names:
        assert name in found, f"missing method {name}"
        assert found[name], f"{name} must call _ro_banner"


def test_prompt_textbox_disabled_in_source():
    src = _panel_source()
    assert 'state="disabled"' in src or "state='disabled'" in src


def test_editable_workers_still_has_save():
    src = _panel_source()
    assert "Сохранить workers.yaml" in src
    assert "def _save_workers" in src
