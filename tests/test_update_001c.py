# -*- coding: utf-8 -*-
from pathlib import Path


def test_status_line_and_banner():
    from ui.update_notice import status_line, should_show_chat_banner

    assert "offline" in status_line({"current": "0.1", "error": "offline"})
    assert should_show_chat_banner({
        "update_available": True,
        "notice": "Доступна 1.0",
    })
    assert not should_show_chat_banner({"update_available": False})


def test_run_update_check_offline():
    from ui.update_notice import run_update_check

    r = run_update_check(offline=True)
    assert r["error"] == "offline"
    assert r.get("notice") == "" or not r.get("update_available")


def test_settings_has_about_tab():
    src = Path("/home/workdir/artifacts/ui/settings_panel.py").read_text(encoding="utf-8")
    assert "_build_about_tab" in src
    assert "run_update_check" in src
    assert "Позже" in src or "about_later" in src


def test_chat_has_maybe_notify():
    src = Path("/home/workdir/artifacts/ui/chat_panel.py").read_text(encoding="utf-8")
    assert "_maybe_notify_update" in src
    assert "AGENTBUS_SKIP_UPDATE_CHECK" in src
