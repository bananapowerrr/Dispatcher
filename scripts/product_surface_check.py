#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Smoke: P0 + PC-GAP product surface (no GUI, no LLM). Exit 0/1."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for p in (ROOT, ROOT / "src", Path("/home/workdir/artifacts"), Path("/home/workdir/artifacts/src")):
    s = str(p)
    if p.exists() and s not in sys.path:
        sys.path.insert(0, s)


def _read(*names: str) -> str:
    for name in names:
        for base in (
            ROOT,
            ROOT / "ui",
            Path("/home/workdir/artifacts"),
            Path("/home/workdir/artifacts/ui"),
        ):
            c = base / name if not str(name).startswith("ui/") else base / Path(name).name
            candidates = [ROOT / name, base / Path(name).name, Path("/home/workdir/artifacts") / name]
            for c in candidates:
                if c.is_file() and c.stat().st_size > 50:
                    return c.read_text(encoding="utf-8", errors="replace")
    return ""


def main() -> int:
    fails: list[str] = []

    sp = _read("ui/settings_panel.py", "settings_panel.py")
    if not sp:
        fails.append("missing settings_panel.py")
    else:
        if "_ro_banner" not in sp:
            fails.append("settings_panel: no _ro_banner")
        if "set_flag(" in sp:
            fails.append("settings_panel: set_flag( still present")
        if "set_active_policy(" in sp:
            fails.append("settings_panel: set_active_policy( still present")

    cp = _read("ui/chat_panel.py", "chat_panel.py")
    if not cp:
        fails.append("missing chat_panel.py")
    else:
        for needle in (
            "format_error_row_for_chat",
            "attach_context_preview",
            "attach_route_preview",
            "format_done_story",
        ):
            if needle not in cp:
                fails.append(f"chat_panel: missing {needle}")

    br = _read("ui/chat_recovery_bridge.py", "chat_recovery_bridge.py")
    if not br or "format_error_row_for_chat" not in br:
        fails.append("chat_recovery_bridge: format_error_row_for_chat missing")

    try:
        from app.settings_contract import is_editable_tab, is_read_only_tab

        assert is_editable_tab("workers")
        assert is_read_only_tab("flags")
    except Exception as e:
        fails.append(f"settings_contract: {e}")

    try:
        from app.product_surface import format_done_story, attach_context_preview

        s = format_done_story({"id": "t1", "result": {"worker": "mock"}})
        assert "✓" in s or "DONE" in s
        c = attach_context_preview("x")
        assert "chat_line" in c
    except Exception as e:
        fails.append(f"product_surface: {e}")

    try:
        from ui.chat_recovery_bridge import format_error_row_for_chat

        out = format_error_row_for_chat({"status": "error", "result": {"error": "e"}})
        assert out.get("kind") == "error"
    except Exception as e:
        fails.append(f"recovery bridge: {e}")

    if fails:
        print("product_surface_check FAIL")
        for f in fails:
            print("  -", f)
        return 1
    print("product_surface_check OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
