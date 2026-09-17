# -*- coding: utf-8 -*-
from pathlib import Path

from app.layout_prefs import get_layout, save_layout, apply_layout_preset, list_layout_presets
from app.task_composer import compose_task, validate_task_dict, format_composer_preview, compose_from_suggestion


def test_layout_roundtrip(tmp_path: Path, monkeypatch):
    cfg = tmp_path / "config"
    cfg.mkdir()
    (cfg / "ui.yaml").write_text("workspace_mode: agent\n", encoding="utf-8")
    # point layout to tmp by chdir
    monkeypatch.chdir(tmp_path)
    lay = save_layout(mode="code", left_width=200, root=tmp_path)
    assert lay["mode"] == "code"
    assert get_layout(tmp_path)["left_width"] == 200
    apply_layout_preset("focus", root=tmp_path)
    assert get_layout(tmp_path)["preset"] == "focus"
    assert len(list_layout_presets()) >= 4


def test_compose_task_basic():
    t = compose_task(message="fix bug in auth", project="/tmp/p", files=["a.py"])
    assert t["message"].startswith("fix")
    assert t["files"] == ["a.py"]
    assert not validate_task_dict(t)
    assert "auth" in format_composer_preview(t)


def test_compose_empty_fails():
    try:
        compose_task(message="  ")
        assert False, "should raise"
    except ValueError:
        pass
