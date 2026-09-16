# -*- coding: utf-8 -*-
from budget import Budget, GLOBAL_BUDGET


def test_real_worker_names():
    assert "aider_openrouter" in GLOBAL_BUDGET.LIMITS
    assert "aider_together" in GLOBAL_BUDGET.LIMITS
    assert "aider_or_free" not in GLOBAL_BUDGET.LIMITS


def test_openrouter_day_limit():
    b = Budget()
    assert b.can_use("aider_openrouter")
    for _ in range(50):
        b.record("aider_openrouter")
    assert not b.can_use("aider_openrouter")
    rem = b.remaining("aider_openrouter")
    assert rem["per_day"] == 0


def test_unlimited_local():
    b = Budget()
    assert b.can_use("aider_local")
    for _ in range(100):
        b.record("aider_local")
    assert b.can_use("aider_local")
