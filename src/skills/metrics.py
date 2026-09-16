# -*- coding: utf-8 -*-
"""Skill hit/success metrics bridge."""
from __future__ import annotations

from typing import Any


def record_skill_hit(name: str, *, success: bool | None = None, latency: float = 0.0) -> None:
    try:
        from utils.metrics import GLOBAL_METRICS
        GLOBAL_METRICS.record("skill_hit")
        if success is True:
            GLOBAL_METRICS.record("skill_success")
        elif success is False:
            GLOBAL_METRICS.record("skill_fail")
        if hasattr(GLOBAL_METRICS, "record_skill"):
            GLOBAL_METRICS.record_skill(name, success=bool(success), latency=latency)
    except Exception:
        pass


def record_skill_miss() -> None:
    try:
        from utils.metrics import GLOBAL_METRICS
        GLOBAL_METRICS.record("skill_miss")
    except Exception:
        pass
