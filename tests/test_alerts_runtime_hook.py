# -*- coding: utf-8 -*-
"""Offline: AlertManager API used by runtime hook."""
from __future__ import annotations

from alerts import AlertManager, GLOBAL_ALERTS


def test_global_alerts_singleton():
    assert GLOBAL_ALERTS is not None


def test_workers_cooldown_alert():
    am = AlertManager(cooldown_sec=0)
    fired = am.check_workers_available(False)
    assert any(a.alert_type == "ALL_WORKERS_COOLDOWN" for a in fired)
    # cooldown suppresses second fire
    am2 = AlertManager(cooldown_sec=9999)
    am2.fire("X", "once")
    assert am2.fire("X", "twice") is None
