from ranking import ExecutorProfile


def test_estimated_latency_requires_three_samples():
    p = ExecutorProfile(key="k")
    p.record(True, latency=12.0, complexity=5, task_type="coding")
    p.record(True, latency=10.0, complexity=5, task_type="coding")
    assert p.estimated_latency(5, "coding") == 0.0


def test_estimated_latency_uses_complexity_bucket():
    p = ExecutorProfile(key="k")
    for latency in (10.0, 20.0, 30.0):
        p.record(True, latency=latency, complexity=5, task_type="coding")
    assert p.estimated_latency(5, "research") == 20.0


def test_estimated_latency_combines_complexity_and_task_type():
    p = ExecutorProfile(key="k")
    for latency in (10.0, 20.0, 30.0):
        p.record(True, latency=latency, complexity=5, task_type="coding")
    for latency in (30.0, 40.0, 50.0):
        p.record(True, latency=latency, complexity=3, task_type="research")
    assert p.estimated_latency(5, "coding") == 20.0
    assert p.estimated_latency(5, "research") == 30.0
