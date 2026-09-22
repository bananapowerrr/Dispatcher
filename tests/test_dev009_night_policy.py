# -*- coding: utf-8 -*-
from datetime import datetime, time
from types import SimpleNamespace


def test_risk_blocks_critical():
    from intelligence.night_policy import filter_by_risk, NightPolicyConfig

    tasks = [
        {"id": "1", "complexity": 5, "metadata": {"risk": "low"}},
        {"id": "2", "complexity": 5, "metadata": {"risk": "critical"}},
    ]
    ok, blocked = filter_by_risk(tasks, NightPolicyConfig())
    assert any(t["id"] == "1" for t in ok)
    assert any(b["id"] == "2" for b in blocked)


def test_select_respects_max_tasks():
    from intelligence.night_policy import select_evening_batch, NightPolicyConfig

    tasks = [
        {"id": str(i), "complexity": 5, "metadata": {"priority": i}, "message": f"t{i}"}
        for i in range(10)
    ]
    cfg = NightPolicyConfig(max_tasks=3, min_complexity=3, require_night_window=False)
    out = select_evening_batch(tasks, cfg=cfg, force=True)
    assert len(out["selected"]) <= 3


def test_outside_night_defers():
    from intelligence.night_policy import select_evening_batch, NightPolicyConfig
    from intelligence.night_scheduler import NightConfig, NightScheduler

    # noon
    now = datetime(2026, 6, 1, 12, 0, 0)
    cfg = NightPolicyConfig(require_night_window=True, min_complexity=1)
    tasks = [{"id": "a", "complexity": 5, "message": "x"}]
    out = select_evening_batch(tasks, cfg=cfg, now=now, force=False)
    assert out["reason"] == "outside_night_window"
    assert out["selected"] == []


def test_plan_night_run_payloads():
    from intelligence.night_policy import plan_night_run, NightPolicyConfig

    tasks = [
        {"id": "a", "complexity": 4, "message": "fix x", "project": "p1", "metadata": {"risk": "low"}},
    ]
    out = plan_night_run(tasks, cfg=NightPolicyConfig(require_night_window=False), force=True)
    assert out["can_start"] is True
    assert out["payloads"]
    assert out["payloads"][0]["metadata"]["night_mode"] is True


def test_morning_report_contains_counts():
    from intelligence.night_policy import build_morning_report
    from intelligence.night_mode_controller import NightSessionResult

    res = NightSessionResult(done=["s0"], errors=["s1"], stopped_reason="complete")
    text = build_morning_report(session_result=res, selection={"selected": [1, 2], "blocked": []})
    assert "Morning Report" in text
    assert "DONE=1" in text
    assert "ERROR=1" in text


def test_run_policy_night_with_loop(tmp_path):
    from intelligence.night_policy import run_policy_night, NightPolicyConfig

    plan = SimpleNamespace(steps=[
        SimpleNamespace(id="s0", title="t0", status="PENDING"),
    ])

    def exec_fn(payload):
        return {"terminal_state": "DONE", "verified": True}

    out = run_policy_night(
        [{"id": "a", "complexity": 5, "message": "x", "metadata": {"risk": "low"}}],
        execute_fn=exec_fn,
        plan=plan,
        cfg=NightPolicyConfig(require_night_window=False, max_tasks=5),
        state_dir=tmp_path,
        force=True,
    )
    assert out["session"] is not None
    assert "Morning Report" in out["morning_report"]
