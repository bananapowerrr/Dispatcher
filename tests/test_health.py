# -*- coding: utf-8 -*-
"""P0: concurrency / health. begin/end как пара, слоты, никакого вечного BUSY."""
from __future__ import annotations
import json
import time

import pytest

from health import HealthRegistry, WorkerState


@pytest.fixture
def reg(tmp_path):
    return HealthRegistry(base_cooldown=10, circuit_limit=3,
                          state_file=tmp_path / "ws.json")


# ---------- семантика слотов ----------
def test_begin_end_pair_releases_slot(reg):
    reg.register("w1", max_parallel=2)
    assert reg.available("w1")
    assert reg.begin_task("w1")
    assert reg.running_count("w1") == 1
    assert reg.running("w1") is False  # есть ещё 1 слот
    assert reg.begin_task("w1")
    assert reg.running("w1") is True   # слоты исчерпаны
    assert not reg.available("w1")
    # третий не влезет
    assert not reg.begin_task("w1")
    reg.end_task("w1")
    reg.end_task("w1")
    assert reg.running_count("w1") == 0
    assert reg.available("w1")


def test_max_parallel_one_default(reg):
    reg.register("solo")  # default max_parallel=1
    assert reg.begin_task("solo")
    assert not reg.available("solo")
    assert not reg.begin_task("solo")
    reg.end_task("solo")
    assert reg.available("solo")


def test_end_task_does_not_go_negative(reg):
    reg.register("w")
    reg.end_task("w")  # без begin — no-op не в -1
    assert reg.running_count("w") == 0


# ---------- cooldown / rate limit блокируют begin ----------
def test_cooldown_blocks_begin(reg):
    reg.register("w")
    reg.state("w").cooldown_until = time.monotonic() + 30
    assert not reg.available("w")
    assert not reg.begin_task("w")


def test_after_success_slot_free(reg):
    reg.register("w", max_parallel=1)
    assert reg.begin_task("w")
    reg.success("w", latency=1.0)
    reg.end_task("w")
    assert reg.available("w")
    assert reg.state("w").status == "AVAILABLE"


def test_after_failure_slot_free_but_cooldown(reg):
    reg.register("w", max_parallel=1)
    assert reg.begin_task("w")
    reg.failure("w", "boom")
    reg.end_task("w")
    assert reg.running_count("w") == 0
    assert reg.state("w").status == "ERROR"
    assert not reg.available("w")  # cooldown


# ---------- нет вечного BUSY после перезагрузки ----------
def test_busy_from_disk_is_available_after_load(tmp_path):
    f = tmp_path / "ws.json"
    f.write_text(json.dumps({
        "w1": {"status": "BUSY", "failures": 2, "cooldown_until": 0,
               "rate_limit_until": 0, "consecutive_failures": 0,
               "consecutive_timeouts": 0, "latency_avg": 0,
               "success_count": 1, "fail_count": 2, "timeout_count": 0,
               "tasks_completed": 1},
        "w2": {"status": "AVAILABLE"},
    }), encoding="utf-8")
    reg = HealthRegistry(state_file=f)
    # w1 был BUSY при падении диспетчера -> теперь свободен
    assert reg.state("w1").status == "AVAILABLE"
    assert reg.available("w1")
    assert reg.state("w1").success_count == 1  # статистика сохранена
    assert reg.state("w1").running_count == 0  # running не персистится


def test_running_count_not_persisted(reg):
    reg.register("w", max_parallel=1)
    reg.begin_task("w")
    data = reg.snapshot()["w"]
    assert "running_count" not in data  # транзиентное поле не пишется


# ---------- конкурентный старт двух слотов ----------
def test_concurrent_begin_limited_to_slots(reg):
    import threading
    reg.register("gpu", max_parallel=2)
    results = []
    stop = False
    lock = threading.Lock()

    def worker():
        ok_taken = 0
        while not stop:
            if reg.begin_task("gpu"):
                with lock:
                    ok_taken += 1
                time.sleep(0.001)
                reg.end_task("gpu")
        with lock:
            results.append(ok_taken)

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for t in threads:
        t.start()
    time.sleep(0.2)
    stop = True
    for t in threads:
        t.join(timeout=5)
    # за это время begin никогда не превысил доступные слоты сверх max_parallel
    assert reg.running_count("gpu") == 0
    assert reg.available("gpu")


def test_score_still_works_with_statuses(reg):
    reg.register("w")
    reg.success("w", latency=2.0)
    s = reg.score("w")
    assert s > 0
    reg.failure("w", "429 rate limited")
    assert reg.score("w") == -1.0  # cooldown -> недоступен