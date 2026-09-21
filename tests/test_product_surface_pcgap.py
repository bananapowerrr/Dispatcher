# -*- coding: utf-8 -*-
from pathlib import Path


def test_format_done_story():
    from app.product_surface import format_done_story

    s = format_done_story(
        {
            "id": "ui-abcdef123",
            "metadata": {"route_preview": {"worker": "aider_local"}},
            "result": {"worker": "aider_local", "changed_files": ["test_aider.txt"]},
        }
    )
    assert "✓ accepted" in s
    assert "aider_local" in s
    assert "test_aider.txt" in s
    assert "DONE" in s


def test_format_error_story_fallback():
    from app.product_surface import format_error_story

    s = format_error_story(
        {"id": "t1", "result": {"error": "verify failed"}, "metadata": {"attempts": 2, "max_attempts": 3}}
    )
    assert "verify failed" in s or "⚠" in s


def test_chat_panel_wires_product_surface():
    roots = [
        Path(__file__).resolve().parents[1] / "ui" / "chat_panel.py",
        Path("/home/workdir/artifacts/ui/chat_panel.py"),
        Path("/home/workdir/artifacts/chat_panel.py"),
    ]
    src = ""
    for p in roots:
        if p.is_file():
            src = p.read_text(encoding="utf-8")
            break
    assert src
    assert "attach_context_preview" in src
    assert "attach_route_preview" in src
    assert "format_done_story" in src
    assert "format_error_row_for_chat" in src


def test_attach_helpers_degrade_without_project():
    from app.product_surface import attach_context_preview, attach_route_preview

    c = attach_context_preview("fix", project="")
    assert "chat_line" in c
    r = attach_route_preview("fix file", project="")
    assert "chat_line" in r
