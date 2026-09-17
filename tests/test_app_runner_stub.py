# -*- coding: utf-8 -*-
from pathlib import Path
from app.app_runner import start_app, stop_app, run_status

def test_start_without_main(tmp_path: Path):
    r = start_app(tmp_path)
    assert r.get("ok") is False
    assert "error" in r

def test_start_stop_main(tmp_path: Path):
    (tmp_path / "main.py").write_text("import time\\ntime.sleep(30)\\n", encoding="utf-8")
    r = start_app(tmp_path)
    assert r.get("ok") is True
    assert run_status().get("running") is True
    s = stop_app()
    assert s.get("ok") is True
    assert run_status().get("running") is False
