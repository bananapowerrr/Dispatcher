# -*- coding: utf-8 -*-
from __future__ import annotations

from intelligence.context_planner import ContextPlanner


def test_planner_render_markers():
    p = ContextPlanner(total_chars=2000)
    plan = p.plan(
        system="You are a coder.",
        task="USER REQUEST: fix bug",
        code="<file_content path=\"a.py\">\nx=1\n</file_content>",
        rag="CODEBASE RAG: a.py related",
        memory="PROJECT MEMORY: use pytest",
    )
    text = plan.render()
    assert "USER REQUEST" in text or "fix bug" in text
    assert "memory" in text.lower() or "PROJECT MEMORY" in text
    assert len(text) <= 2500


class _Dummy:
    def _apply_context_planner_budget(self, message, *, sys_prompt=""):
        from core.rp_context import RPContextMixin
        return RPContextMixin._apply_context_planner_budget(self, message, sys_prompt=sys_prompt)


def test_runtime_helper_does_not_empty():
    d = _Dummy()
    msg = "PROJECT MEMORY: rule\n\nUSER REQUEST: do thing\n\n<code>\ndef x():\n  pass\n</code>"
    out = d._apply_context_planner_budget(msg, sys_prompt="sys")
    assert len(out) > 10
    assert "do thing" in out or "USER REQUEST" in out
