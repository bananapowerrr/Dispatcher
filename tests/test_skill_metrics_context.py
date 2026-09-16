# -*- coding: utf-8 -*-
from __future__ import annotations

from utils.metrics import MetricsCollector
from intelligence.context_planner import ContextPlanner


def test_record_skill_stats():
    m = MetricsCollector()
    m.record_skill("format_code", success=True, latency=0.05)
    m.record_skill("format_code", success=False, latency=0.02)
    m.record_skill("rename_symbol", success=True, latency=0.1)
    rates = m.get_hit_rates()
    by = rates.get("skill_by_name") or {}
    assert "format_code" in by
    assert by["format_code"]["hits"] == 2
    assert by["format_code"]["success"] == 1
    assert by["rename_symbol"]["success_rate"] == 1.0


def test_context_planner_budget():
    p = ContextPlanner(total_chars=1000)
    plan = p.plan(
        system="S" * 500,
        task="T" * 500,
        code="C" * 5000,
        rag="R" * 500,
        memory="M" * 500,
    )
    assert len(plan.system) <= p.budget("system") + 30
    assert len(plan.code) <= p.budget("code") + 30
    text = plan.render()
    assert "<code>" in text
    assert plan.to_dict()["total_chars"] == 1000
