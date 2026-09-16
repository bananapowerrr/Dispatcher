# -*- coding: utf-8 -*-
from __future__ import annotations

from core.timeout_policy import (
    clamp_exec_timeout,
    complexity_factor,
    stuck_timeout_sec,
    suggest_exec_timeout,
)


def test_clamp_bounds():
    assert clamp_exec_timeout(5) == 15
    assert clamp_exec_timeout(99999) <= 10_000
    assert 15 <= clamp_exec_timeout(300) <= 1800


def test_complexity_factor_monotone():
    assert complexity_factor(1) < complexity_factor(5)


def test_suggest_scales():
    t1 = suggest_exec_timeout(worker_timeout=300, complexity=1)
    t5 = suggest_exec_timeout(worker_timeout=300, complexity=5)
    assert t5 >= t1


def test_stuck_explicit():
    t = stuck_timeout_sec({"metadata": {"stuck_timeout_sec": 120}})
    assert 60 <= t <= 1800
