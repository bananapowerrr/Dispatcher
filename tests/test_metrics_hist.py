# -*- coding: utf-8 -*-
from metrics import MetricsCollector


def test_duration_histogram_buckets():
    m = MetricsCollector()
    m.record_task({"id": "a"}, "w", True, latency=5.0)
    m.record_task({"id": "b"}, "w", True, latency=45.0)
    m.record_task({"id": "c", "metadata": {"attempts": 3}}, "w", False, latency=150.0, status="ERROR")
    s = m.get_summary()
    assert s["duration_histogram"]["0-10s"] >= 1
    assert s["duration_histogram"]["30-60s"] >= 1
    assert s["duration_histogram"]["120s+"] >= 1
    assert s["retry_histogram"]["3+"] >= 1
    assert s["task_count"] == 3
