# -*- coding: utf-8 -*-
from pathlib import Path
from intelligence.living_plan import LivingPlan, LivingStep, save_living_plan, load_living_plan

def test_corrupt_plan_returns_empty_not_crash(tmp_path: Path):
    p = tmp_path / ".agentbus"
    p.mkdir(parents=True)
    (p / "living_plan.json").write_text("{not-json", encoding="utf-8")
    plan = load_living_plan(tmp_path)
    assert plan.steps == [] or len(plan.steps) == 0

def test_save_roundtrip(tmp_path: Path):
    plan = LivingPlan(version=2, summary="x")
    plan.steps.append(LivingStep(id="a", action="A", status="PENDING"))
    save_living_plan(tmp_path, plan)
    loaded = load_living_plan(tmp_path)
    assert loaded.version == 2
    assert loaded.get("a").action == "A"
    assert (tmp_path / ".agentbus" / "living_plan.json").is_file()

def test_safe_log_import():
    from utils.safe_log import warn, error
    warn("test", "hello %s", "x")
    error("test", "err")
