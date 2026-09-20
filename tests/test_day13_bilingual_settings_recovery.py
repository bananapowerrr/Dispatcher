# -*- coding: utf-8 -*-
"""Day-13 offline: bilingual parity, settings contract, recovery chat bridge."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

# Allow importing from artifacts / src when run offline
ROOT = Path(__file__).resolve().parents[1]
for p in (ROOT, ROOT / "src", Path("/home/workdir/artifacts")):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))


def _load_strings(name: str) -> dict:
    # Prefer repo config if present, else artifacts snapshot
    candidates = [
        ROOT / "config" / name,
        Path("/home/workdir/artifacts") / name,
    ]
    for c in candidates:
        if c.is_file():
            data = yaml.safe_load(c.read_text(encoding="utf-8")) or {}
            assert isinstance(data, dict)
            return data
    pytest.skip(f"missing {name}")


def test_strings_en_ru_key_parity():
    en = _load_strings("strings_en.yaml")
    ru = _load_strings("strings_ru.yaml")
    only_en = sorted(set(en) - set(ru))
    only_ru = sorted(set(ru) - set(en))
    assert only_en == [], f"EN-only keys: {only_en}"
    assert only_ru == [], f"RU-only keys: {only_ru}"
    assert len(en) >= 160


def test_parity_keys_have_nonempty_values():
    en = _load_strings("strings_en.yaml")
    ru = _load_strings("strings_ru.yaml")
    for k in ("no_project", "no_selection", "run_app", "stop_app", "suggest"):
        assert str(en.get(k) or "").strip(), k
        assert str(ru.get(k) or "").strip(), k


def test_settings_contract_editable_vs_readonly():
    from settings_contract import (
        EDITABLE_TABS,
        READ_ONLY_TABS,
        is_editable_tab,
        is_read_only_tab,
        settings_contract_summary,
    )

    assert "workers" in EDITABLE_TABS
    assert "providers" in READ_ONLY_TABS
    assert EDITABLE_TABS.isdisjoint(READ_ONLY_TABS)
    assert is_editable_tab("workers")
    assert is_editable_tab("Воркеры")
    assert is_read_only_tab("providers")
    assert is_read_only_tab("Провайдеры")
    s = settings_contract_summary()
    assert "editable" in s and "read_only" in s


def test_recovery_bridge_formats_error_block():
    # Prefer app.recovery_ux if on path; else import local recovery_ux artifact
    try:
        from chat_recovery_bridge import format_recovery_for_chat, merge_terminal_with_recovery
    except ImportError:
        sys.path.insert(0, "/home/workdir/artifacts")
        from chat_recovery_bridge import format_recovery_for_chat, merge_terminal_with_recovery

    # Stub recovery_ux if package missing
    try:
        import app.recovery_ux  # noqa: F401
    except Exception:
        import types

        mod = types.ModuleType("app")
        rx = types.ModuleType("app.recovery_ux")

        def format_recovery_bundle(**kwargs):
            return "⚠ test\n↻ Replan: шаг `e1`\n→ Добавлен retry-шаг `n1`"

        rx.format_recovery_bundle = format_recovery_bundle
        sys.modules["app"] = mod
        sys.modules["app.recovery_ux"] = rx

    out = format_recovery_for_chat(
        task_error="timeout",
        replan={"ok": True, "error_step_id": "e1", "new_step_id": "n1"},
        attempts=1,
        max_attempts=3,
    )
    assert out["kind"] == "error"
    assert out["chat"]
    assert "phase" in out

    merged = merge_terminal_with_recovery(
        {"chat": "⚠ base", "phase": "err", "kind": "error"},
        out,
    )
    assert merged["kind"] == "error"
    assert "base" in merged["chat"] or merged["chat"]


def test_recovery_ux_still_pure_formatters():
    try:
        from app.recovery_ux import format_block_reason, format_replan_result
    except Exception:
        sys.path.insert(0, "/home/workdir/artifacts")
        # recovery_ux was downloaded to artifacts root
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "recovery_ux", "/home/workdir/artifacts/recovery_ux.py"
        )
        mod = importlib.util.module_from_spec(spec)
        assert spec and spec.loader
        spec.loader.exec_module(mod)
        format_block_reason = mod.format_block_reason
        format_replan_result = mod.format_replan_result

    assert "План" in format_block_reason({"block": True, "reason": "decision needed"})
    ok = format_replan_result(
        {"ok": True, "error_step_id": "s1", "new_step_id": "s2"}
    )
    assert "s2" in ok and "PENDING" in ok
