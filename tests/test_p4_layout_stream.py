# -*- coding: utf-8 -*-
from pathlib import Path
from app.layout_prefs import apply_layout_preset, get_layout, save_layout
from app import app_runner
from app.event_tail import format_event_line, filter_important, drain_events


def test_layout_presets(tmp_path: Path):
    (tmp_path / "config").mkdir()
    layout = apply_layout_preset("focus", root=tmp_path)
    assert layout.get("mode") in ("code", "focus") or layout.get("preset") == "focus"
    loaded = get_layout(tmp_path)
    assert isinstance(loaded, dict)


def test_drain_new_output_api():
    assert hasattr(app_runner, "drain_new_output")
    assert isinstance(app_runner.drain_new_output(), list)


def test_event_tail_format():
    line = format_event_line({"type": "DONE", "task_id": "t1", "message": "ok"})
    assert "DONE" in line
    assert filter_important([{"type": "HEARTBEAT"}, {"type": "ERROR"}])[0]["type"] == "ERROR"


def test_main_has_stream_and_layout():
    src = Path("ui/main_window.py").read_text(encoding="utf-8")
    assert "_stream_app_output" in src
    assert "_poll_eventbus" in src
    assert "_apply_layout_preset" in src
    assert "Control-Alt-1" in src
    cmds = Path("ui/commands.py").read_text(encoding="utf-8")
    assert "layout.agent" in cmds
    assert "layout.save" in cmds
