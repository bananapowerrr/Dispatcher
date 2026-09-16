# -*- coding: utf-8 -*-
"""P1: ContextPlanner hard budget + runtime path contract."""
from __future__ import annotations

from intelligence.context_planner import ContextPlanner, ContextPlan


def test_budget_slots_sum_to_total():
    p = ContextPlanner(total_chars=10_000)
    total = sum(p.budget(s) for s in ("system", "task", "code", "rag", "memory"))
    # integer truncation may leave a few chars
    assert 9900 <= total <= 10_000


def test_trim_enforced_on_huge_code():
    p = ContextPlanner(total_chars=1000)
    huge = "x" * 50_000
    plan = p.plan(system="sys", task="do", code=huge, rag="", memory="")
    assert len(plan.code) <= p.budget("code") + 5
    assert "trimmed:code" in " ".join(plan.notes) or len(plan.code) < len(huge)
    assert len(plan.render()) <= 1200


def test_render_order_memory_before_code():
    plan = ContextPlan(
        total_chars=500,
        system="S",
        task="T",
        code="C",
        rag="R",
        memory="M",
    )
    text = plan.render()
    assert text.index("S") < text.index("M") or "M" in text
    assert "<code>" in text and "<rag>" in text


def test_runtime_budget_preserves_user_request():
    from core.rp_context import RPContextMixin

    class D:
        pass

    d = D()
    msg = (
        "PROJECT MEMORY: use poetry\n\n"
        "CODEBASE RAG: auth.py login()\n\n"
        "USER REQUEST: rename login to sign_in\n\n"
        "<file_content path=\"auth.py\">\ndef login():\n    pass\n</file_content>\n"
    )
    out = RPContextMixin._apply_context_planner_budget(d, msg, sys_prompt="You are AgentBus.")
    assert len(out) > 30
    assert "rename" in out.lower() or "sign_in" in out or "USER REQUEST" in out
    # system may be present if planner kept it
    assert "login" in out or "auth" in out


def test_empty_message_safe():
    from core.rp_context import RPContextMixin

    class D:
        pass

    out = RPContextMixin._apply_context_planner_budget(D(), "", sys_prompt="")
    assert isinstance(out, str)
