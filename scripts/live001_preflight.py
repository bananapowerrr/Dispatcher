#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Day-17 offline preflight before LIVE-001 on PC.

Checks product surfaces (Days 6–16) and environment hints.
Does not start Ollama/Aider or mutate Runtime/FSM.

Usage (repo root):
  PYTHONPATH=src:. python scripts/live001_preflight.py
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

CHECKS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    CHECKS.append((name, ok, detail))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))


def _try_import(mod: str) -> tuple[bool, str]:
    try:
        importlib.import_module(mod)
        return True, "ok"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def main() -> int:
    print("=== LIVE-001 preflight (offline-safe) ===\n")

    # Core freeze surfaces still importable
    for mod in (
        "core.worker_route",
        "core.worker_route_surface",
        "app.settings_contract",
        "app.recovery_ux",
        "ui.chat_recovery_bridge",
        "ui.chat_task_bridge",
        "intelligence.file_selector",
        "intelligence.context_report",
    ):
        ok, detail = _try_import(mod)
        check(f"import:{mod}", ok, detail)

    # Source contracts
    panel = ROOT / "ui" / "settings_panel.py"
    if panel.is_file():
        text = panel.read_text(encoding="utf-8")
        check(
            "settings_ro_enforced",
            "set_flag(" not in text and "_ro_banner" in text,
            "RO tabs must not call set_flag",
        )
    else:
        check("settings_ro_enforced", False, "ui/settings_panel.py missing")

    chat = ROOT / "ui" / "chat_panel.py"
    if chat.is_file():
        text = chat.read_text(encoding="utf-8")
        check(
            "chat_recovery_wired",
            "format_error_row_for_chat" in text,
            "ERROR path enrichment",
        )
    else:
        check("chat_recovery_wired", False, "ui/chat_panel.py missing")

    # Functional smoke (no network)
    try:
        from intelligence.context_report import format_context_report

        t = format_context_report(project_root=None, message="LIVE-001")
        check("context_report_text", "Project:" in t, t.split("\n")[0][:50])
    except Exception as e:
        check("context_report_text", False, str(e)[:80])

    try:
        from core.worker_route_surface import format_route_for_chat
        from types import SimpleNamespace

        w = SimpleNamespace(
            name="aider_local",
            provider="ollama",
            enabled=True,
            role="code",
            model="qwen2.5-coder:7b",
            timeout=120,
            max_parallel=1,
            harness="aider",
            priority=50,
        )
        text = format_route_for_chat("Создай test_aider.txt", workers=[w])
        check("route_sample", "WORKER ROUTE" in text, text.split("\n")[1][:60] if "\n" in text else "")
    except Exception as e:
        check("route_sample", False, str(e)[:80])

    try:
        from ui.chat_recovery_bridge import format_error_row_for_chat

        out = format_error_row_for_chat(
            {
                "status": "error",
                "result": {"error": "verify failed", "worker": "aider_local"},
                "metadata": {
                    "attempts": 1,
                    "replan": {"ok": True, "error_step_id": "s1", "new_step_id": "s1r"},
                },
            }
        )
        check("recovery_error_block", out.get("kind") == "error" and bool(out.get("chat")), "")
    except Exception as e:
        check("recovery_error_block", False, str(e)[:80])

    # Env hints (informational — not hard fail)
    print("\n--- environment hints (informational) ---")
    try:
        import urllib.request

        urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=1.5)
        print("  [hint] Ollama: reachable at 127.0.0.1:11434")
    except Exception:
        print("  [hint] Ollama: not reachable (expected offline; required for LIVE-001)")

    import shutil

    for cli in ("aider", "ollama"):
        path = shutil.which(cli)
        print(f"  [hint] CLI {cli}: {path or 'NOT FOUND'}")

    passed = sum(1 for _, ok, _ in CHECKS if ok)
    total = len(CHECKS)
    print(f"\n=== preflight {passed}/{total} PASS ===")
    if passed == total:
        print("Ready for PC LIVE-001 sequence — see docs/DAY17_LIVE001_GATE.md")
        return 0
    print("Fix FAIL rows before attempting live Aider cycle")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
