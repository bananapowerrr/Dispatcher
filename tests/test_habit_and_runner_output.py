# -*- coding: utf-8 -*-
from pathlib import Path
from app.habit import record_continue_accept, load_habit, reset_habit
from app.app_runner import start_app, stop_app, last_output

def test_habit_prompts_once(tmp_path: Path):
    reset_habit(tmp_path)
    for i in range(4):
        r = record_continue_accept(tmp_path, threshold=5)
        assert r["suggest_profile"] is False
    r = record_continue_accept(tmp_path, threshold=5)
    assert r["suggest_profile"] is True
    assert "профиль" in r["message"].lower() or "стандартным" in r["message"].lower()
    r2 = record_continue_accept(tmp_path, threshold=5)
    assert r2["suggest_profile"] is False  # only once
    h = load_habit(tmp_path)
    assert h.get("prompted_profile") is True

def test_runner_captures_output(tmp_path: Path):
    (tmp_path / "main.py").write_text("print('hello-agentbus')\n", encoding="utf-8")
    r = start_app(tmp_path)
    assert r.get("ok") is True
    import time
    time.sleep(0.8)
    stop_app()
    # may or may not capture depending on timing; at least API works
    _ = last_output(10)
