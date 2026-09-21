#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Day 21+: import/source smoke for product surface (no GUI, no LLM).

Exit 0 if P0 contracts visible in tree; 1 otherwise.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))


def _read(rel: str) -> str:
    for base in (ROOT, ROOT / "ui", Path("/home/workdir/artifacts"), Path("/home/workdir/artifacts/ui")):
        p = base / rel if not rel.startswith("ui/") else base / rel.replace("ui/", "")
        # try exact
        candidates = [
            ROOT / rel,
            Path("/home/workdir/artifacts") / rel,
            Path("/home/workdir/artifacts") / Path(rel).name,
        ]
        for c in candidates:
            if c.is_file():
                return c.read_text(encoding="utf-8", errors="replace")
    return ""


def main() -> int:
    fails: list[str] = []

    # settings panel RO
    sp = _read("ui/settings_panel.py") or _read("settings_panel.py")
    if not sp:
        fails.append("missing settings_panel.py")
    else:
        if "_ro_banner" not in sp:
            fails.append("settings_panel: no _ro_banner (stale copy?)")
        if "set_flag(" in sp:
            fails.append("settings_panel: set_flag( still present")
        if "set_active_policy(" in sp:
            fails.append("settings_panel: set_active_policy( still present")

    # chat ERROR wire
    cp = _read("ui/chat_panel.py") or _read("chat_panel.py")
    if not cp:
        fails.append("missing chat_panel.py")
    elif "format_error_row_for_chat" not in cp:
        fails.append("chat_panel: no format_error_row_for_chat (P0-2 not synced)")

    br = _read("ui/chat_recovery_bridge.py") or _read("chat_recovery_bridge.py")
    if not br:
        fails.append("missing chat_recovery_bridge.py")
    elif "format_error_row_for_chat" not in br:
        fails.append("chat_recovery_bridge: no format_error_row_for_chat")

    # contract module
    try:
        from app.settings_contract import is_editable_tab, is_read_only_tab

        assert is_editable_tab("workers")
        assert is_read_only_tab("flags")
    except Exception as e:
        fails.append(f"settings_contract import: {e}")

    # recovery format
    try:
        from ui.chat_recovery_bridge import format_recovery_for_chat, format_error_row_for_chat

        out = format_recovery_for_chat(task_error="x", attempts=1)
        assert out.get("kind") == "error"
        row = format_error_row_for_chat({"status": "error", "result": {"error": "e"}})
        assert row.get("kind") == "error"
    except Exception as e:
        fails.append(f"recovery bridge: {e}")

    # optional surfaces (warn only)
    warns: list[str] = []
    for mod, attr in (
        ("intelligence.context_report", "build_context_report"),
        ("core.worker_route_surface", "route_for_task"),
        ("core.live_fail_layer", "classify_error_text"),
    ):
        try:
            m = __import__(mod, fromlist=[attr])
            getattr(m, attr)
        except Exception as e:
            warns.append(f"{mod}.{attr}: {e}")

    if fails:
        print("product_surface_check FAIL")
        for f in fails:
            print("  -", f)
        for w in warns:
            print("  warn:", w)
        return 1
    print("product_surface_check OK (P0 surface visible)")
    for w in warns:
        print("  warn:", w)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
