# -*- coding: utf-8 -*-
"""Edge cases для safety/health.py: cooldown-ступени, гонки, границы времени.

Покрывает то, чего нет в test_health.py:
  * ступенчатый (LOOP) cooldown 60 -> 120 -> 300 -> 900 -> 1800 и его потолок;
  * success() обнуляет consecutive_failures/cooldown, но НЕ rate_limit;
  * available()/effective_status() на границе cooldown_until == now;
  * параллельные begin_task/end_task и end_task без begin;
  * billing / rate-limit / verify-DEGRADED ветки;
  * circuit limit (base*3 / base*4 для таймаутов);
  * битое/отсутствующее state-файл, save_state при ошибке ФС.

Время контролируется подменой time.monotonic в модуле safety.health,
поэтому тесты не ждут реальных минут.
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import pytest

from safety import health as health_mod
from safety.health import HealthRegistry, WorkerState


# --------------------------------------------------------------------------
# helpers / fixtures
# --------------------------------------------------------------------------
class _FakeClock:
    """Подмена time.monotonic: двигаем время только мы."""

    def __init__(self, start: float = 1000.0) -> None:
        self.now = float(start)

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += float(seconds)


@pytest.fixture
def clock(monkeypatch):
    """Весь health.py читает время только через time.monotonic()."""
    c = _FakeClock()
    monkeypatch.setattr(health_mod.time, "monotonic", c)
    return c


@pytest.fixture
def reg(tmp_path, clock):
    return _no_budget_registry(tmp_path, base_cooldown=60, circuit_limit=3)


# --------------------------------------------------------------------------
# 1. Экспоненциальный (ступенчатый) cooldown LOOP
# --------------------------------------------------------------------------
@pytest.mark.parametrize("n,expected", [(1, 60.0), (2, 120.0), (3, 300.0),
                                        (4, 900.0), (5, 1800.0)])
def test_loop_cooldown_tier_n_failure_expected_seconds(reg, clock, n, expected):
    """1 fail -> 60s, 2 -> 120s, 3 -> 300s (ступени LOOP, не плоские 300s)."""
    reg.register("w")
    for _ in range(n):
        reg.failure("w", "loop detected", status="LOOP")
    st = reg.state("w")
    assert st.cooldown_until - clock.now == pytest.approx(expected)
    assert st.status == "LOOP"


def test_loop_cooldown_capped_at_last_tier(reg, clock):
    """Свых 5-й ступени cooldown не растёт (потолок 1800s)."""
    reg.register("w")
    for _ in range(12):
        reg.failure("w", "loop detected", status="LOOP")
    st = reg.state("w")
    assert st.cooldown_until - clock.now == pytest.approx(1800.0)
    assert st.consecutive_failures == 12


def test_loop_cooldown_detected_by_russian_marker(reg, clock):
    """LOOP распознаётся по тексту ошибки, даже без status='LOOP'."""
    reg.register("w")
    reg.failure("w", "Воркер зацикливание: повтор шага 1", status="ERROR")
    st = reg.state("w")
    assert st.status == "LOOP"
    assert st.cooldown_until - clock.now == pytest.approx(60.0)


def test_error_cooldown_uses_fail_tiers_not_loop_tiers(reg, clock):
    """Обычная ошибка идёт по _FAIL_TIERS (60, 300, 900, ...) — не по LOOP."""
    reg.register("w")
    reg.failure("w", "boom")
    assert reg.state("w").status == "ERROR"
    assert reg.state("w").cooldown_until - clock.now == pytest.approx(60.0)
    reg.failure("w", "boom again")
    # вторая ошибка: _FAIL_TIERS[1] = 300, и circuit_limit тут ещё не достигнут
    assert reg.state("w").cooldown_until - clock.now == pytest.approx(300.0)


# --------------------------------------------------------------------------
# 2. success() сбрасывает серию сбоев и cooldown
# --------------------------------------------------------------------------
def test_success_resets_consecutive_failures_and_cooldown(reg, clock):
    reg.register("w")
    for _ in range(3):
        reg.failure("w", "boom")
    assert reg.state("w").consecutive_failures == 3
    assert reg.state("w").cooldown_until > clock.now

    reg.success("w")

    st = reg.state("w")
    assert st.consecutive_failures == 0
    assert st.cooldown_until == 0.0
    assert st.failures == 0
    assert st.status == "AVAILABLE"


def test_success_does_not_clear_rate_limit_until(reg, clock):
    """rate_limit_until — ограничение провайдера, а не здоровья воркера."""
    reg.register("w")
    reg.failure("w", "429 too many requests")
    assert reg.state("w").rate_limit_until > clock.now
    reg.success("w")
    st = reg.state("w")
    assert st.cooldown_until == 0.0
    assert st.rate_limit_until > clock.now, "success не должен снимать rate limit"
    assert reg.available("w") is False


def test_success_after_failures_restores_loop_tier_to_first(reg, clock):
    """После успеха ступень LOOP начинается заново с 60s, а не с 1800s."""
    reg.register("w")
    for _ in range(5):
        reg.failure("w", "loop detected", status="LOOP")
    reg.success("w")
    reg.failure("w", "loop detected", status="LOOP")
    assert reg.state("w").cooldown_until - clock.now == pytest.approx(60.0)


def test_success_zero_latency_is_treated_as_no_measurement(reg):
    """latency=0 — это «нет замера», а не нулевая задержка.

    `success()` гардит `if latency:`, поэтому вызов с 0.0 не двигает EWMA
    (иначе среднее нырнуло бы к нулю после задачи с мгновенным ответом).
    """
    reg.register("w")
    reg.success("w", latency=10.0)
    reg.success("w", latency=0.0)
    st = reg.state("w")
    assert st.latency_avg == pytest.approx(10.0)
    assert st.success_count == 2
    assert st.tasks_completed == 2


def test_success_latency_ewma_weighted_by_success_count(reg):
    reg.register("w")
    reg.success("w", latency=10.0)
    reg.success("w", latency=20.0)
    assert reg.state("w").latency_avg == pytest.approx(15.0)


def test_success_resets_verify_failure_series(reg):
    reg.register("w")
    reg.verify_failure("w", "bad")
    reg.verify_failure("w", "bad")
    assert reg.state("w").consecutive_verify_failures == 2
    reg.success("w")
    assert reg.state("w").consecutive_verify_failures == 0


def test_verify_success_resets_series_and_degraded(reg, clock):
    reg.register("w")
    for _ in range(3):
        reg.verify_failure("w", "bad")
    assert reg.state("w").status == "DEGRADED"
    reg.verify_success("w")
    st = reg.state("w")
    assert st.consecutive_verify_failures == 0
    assert st.status == "AVAILABLE"
    # verify_success НЕ снимает cooldown, выставленный verify-серией
    assert st.cooldown_until > clock.now


# --------------------------------------------------------------------------
# 3. available() / begin_task() на границе времени
# --------------------------------------------------------------------------
def test_available_false_while_cooldown_in_future(reg, clock):
    reg.register("w")
    reg.failure("w", "boom")
    assert reg.available("w") is False
    clock.advance(59.9)
    assert reg.available("w") is False


def test_available_true_at_exact_cooldown_boundary(reg, clock):
    """Ровно на границе (now == cooldown_until) воркер доступен (>=)."""
    reg.register("w")
    reg.failure("w", "boom")
    clock.advance(60.0)
    assert reg.available("w") is True


def test_begin_task_blocked_during_rate_limit_only(reg, clock):
    reg.register("w")
    reg.failure("w", "429 rate limit")
    reg.success("w")  # cooldown снят, rate_limit остался
    assert reg.state("w").cooldown_until == 0.0
    assert reg.begin_task("w") is False


def test_begin_task_registered_slots_exhausted_returns_false(reg):
    reg.register("w", max_parallel=1)
    assert reg.begin_task("w") is True
    assert reg.running("w") is True
    assert reg.begin_task("w") is False


def test_register_clamps_max_parallel_to_at_least_one(reg):
    """max_parallel=0 / None / -5 не должны открывать бесконечные слоты."""
    reg.register("z", max_parallel=0)
    reg.register("n", max_parallel=None)
    reg.register("neg", max_parallel=-5)
    assert reg.max_parallel["z"] == 1
    assert reg.max_parallel["n"] == 1
    assert reg.max_parallel["neg"] == 1
    assert reg.begin_task("neg") is True
    assert reg.begin_task("neg") is False


def test_budget_denies_begin_task(reg):
    reg.register("w")
    reg.budget = type("NoBudget", (), {
        "can_use": lambda self, name: False,
        "record": lambda self, name, tokens=0: None,
    })()
    assert reg.begin_task("w") is False
    assert reg.running_count("w") == 0


# --------------------------------------------------------------------------
# 4. Гонки: параллельные begin/end
# --------------------------------------------------------------------------
def test_parallel_begin_task_never_exceeds_max_parallel(reg):
    """N потоков x M попыток: успешных begin ровно max_parallel."""
    reg.register("gpu", max_parallel=3)
    acquired: list[bool] = []
    lock = threading.Lock()
    barrier = threading.Barrier(8)

    def worker():
        barrier.wait()
        for _ in range(50):
            if reg.begin_task("gpu"):
                with lock:
                    acquired.append(True)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    assert len(acquired) == 3, "слиплись слоты: begin_task не под локом"
    assert reg.running_count("gpu") == 3
    assert reg.available("gpu") is False


def test_parallel_end_task_never_goes_negative(reg):
    """end_task без пары begin не уводит running_count в -1 (max(0, ...))."""
    reg.register("w")
    reg.begin_task("w")
    barrier = threading.Barrier(8)

    def worker():
        barrier.wait()
        for _ in range(20):
            reg.end_task("w")

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    assert reg.running_count("w") == 0
    assert reg.available("w") is True


def test_parallel_begin_and_end_leaves_no_forever_busy(reg):
    """Смешанная нагрузка: после потоков статус не должен залипнуть в BUSY."""
    reg.register("w", max_parallel=2)
    barrier = threading.Barrier(6)

    def worker():
        barrier.wait()
        for _ in range(30):
            if reg.begin_task("w"):
                reg.end_task("w")

    threads = [threading.Thread(target=worker) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    assert reg.running_count("w") == 0
    assert reg.state("w").status != "BUSY"
    assert reg.available("w") is True


def test_end_task_ok_false_records_failure(reg, clock):
    """ok=False обязан фиксировать failure (иначе воркер снова выберется)."""
    reg.register("w")
    reg.begin_task("w")
    reg.end_task("w", ok=False, error="preflight: runtime недоступен", status="ERROR")
    st = reg.state("w")
    assert st.running_count == 0
    assert st.consecutive_failures == 1
    assert st.status == "ERROR"
    assert st.cooldown_until > clock.now
    assert "preflight" in st.last_error


def test_end_task_ok_false_defaults_error_when_empty(reg):
    reg.register("w")
    reg.begin_task("w")
    reg.end_task("w", ok=False, status="PREFLIGHT")
    assert "PREFLIGHT" in reg.state("w").last_error


def test_end_task_ok_false_zero_negative_running_count(reg):
    """ok=False без begin: слот не уходит в минус, но failure засчитывается."""
    reg.register("w")
    reg.end_task("w", ok=False, error="boom")
    assert reg.running_count("w") == 0
    assert reg.state("w").failures == 1


def test_end_task_ok_true_only_frees_slot_and_leaves_health_untouched(reg, clock):
    """end_task(ok=True) НЕ чинит здоровье — это зона success().

    Ошибка была в обратную сторону: ok=False игнорировался. Симметрично,
    ok=True не должен обнулять cooldown/rate_limit — вызывающий обязан
    звать success(), который это делает осознанно.
    """
    reg.register("w")
    reg.failure("w", "retry-after: 42")
    cooldown_before = reg.state("w").cooldown_until
    reg.begin_task = lambda *a, **k: True  # слот занят воркером до rate limit
    reg.end_task("w", ok=True)
    st = reg.state("w")
    assert st.running_count == 0
    assert st.cooldown_until == cooldown_before
    assert st.rate_limit_until > clock.now
    assert reg.available("w") is False


# --------------------------------------------------------------------------
# 5. Billing / rate limit / circuit limit
# --------------------------------------------------------------------------
def test_billing_error_sets_24h_cooldown_and_skips_tiers(reg, clock):
    reg.register("w")
    for _ in range(3):
        reg.failure("w", "402 insufficient credits")
    st = reg.state("w")
    assert st.status == "BILLING"
    assert st.cooldown_until - clock.now == pytest.approx(86400.0)
    assert st.consecutive_failures == 3, "billing не должен разгонять circuit"


def test_billing_flag_overrides_error_text(reg, clock):
    reg.register("w")
    reg.failure("w", "connection reset", billing_error=True)
    assert reg.state("w").status == "BILLING"


def test_retry_after_header_sets_rate_limit_until(reg, clock):
    reg.register("w")
    reg.failure("w", "HTTP 429 retry-after: 42")
    st = reg.state("w")
    assert st.status == "RATE_LIMITED"
    assert st.rate_limit_until - clock.now == pytest.approx(42.0)
    assert st.cooldown_until - clock.now == pytest.approx(60.0)  # не меньше base


def test_retry_after_capped_at_24h(reg, clock):
    reg.register("w")
    reg.failure("w", "retry after 999999")
    assert reg.state("w").rate_limit_until - clock.now <= 86400.0


def test_generic_rate_limit_uses_rate_tiers(reg, clock):
    reg.register("w")
    reg.failure("w", "too many requests")
    st = reg.state("w")
    assert st.status == "RATE_LIMITED"
    assert st.rate_limit_until - clock.now == pytest.approx(300.0)  # _RATE_TIERS[1]


def test_circuit_limit_multiplies_base_cooldown_by_three(tmp_path, clock):
    """consecutive_failures >= circuit_limit -> base*3 (если ступень не выше).

    Нужен base больше _FAIL_TIERS, иначе ступень провайла всегда выше и
    множитель circuit не виден снаружи.
    """
    r = _no_budget_registry(tmp_path, base_cooldown=600, circuit_limit=3)
    r.register("w")
    r.failure("w", "boom")
    r.failure("w", "boom")
    assert r.state("w").cooldown_until - clock.now == pytest.approx(600.0)
    r.failure("w", "boom")  # circuit_limit достигнут -> 600 * 3
    st = r.state("w")
    assert st.consecutive_failures >= r.circuit_limit
    assert st.cooldown_until - clock.now == pytest.approx(600 * 3)


def test_timeout_circuit_limit_uses_base_times_three_not_four(tmp_path, clock):
    """Ветка base*4 для таймаутов недостижима: счётчики сбрасываются вместе.

    `consecutive_timeouts` — подмножество `consecutive_failures` (оба
    обнуляются в success()), поэтому условие `consecutive_failures >=
    circuit_limit` всегда срабатывает первым, а `elif` по таймаутам —
    мёртвый код. Таймаут получает base*3, как и обычная ошибка.
    """
    r = _no_budget_registry(tmp_path, base_cooldown=600, circuit_limit=3)
    r.register("w")
    for _ in range(3):
        r.failure("w", "timeout", timed_out=True)
    st = r.state("w")
    assert st.status == "TIMEOUT"
    assert st.timeout_count == 3
    assert st.consecutive_timeouts == st.consecutive_failures
    assert st.cooldown_until - clock.now == pytest.approx(600 * 3)


def test_last_error_truncated_to_2000_chars(reg):
    reg.register("w")
    reg.failure("w", "x" * 5000)
    assert len(reg.state("w").last_error) == 2000


# --------------------------------------------------------------------------
# 6. score() на границах
# --------------------------------------------------------------------------
def test_score_returns_minus_one_when_unavailable(reg, clock):
    reg.register("w")
    reg.failure("w", "boom")
    assert reg.score("w") == -1.0


def test_score_zero_for_unavailable_worker_regardless_of_history(reg, clock):
    reg.register("w")
    for _ in range(20):
        reg.success("w", latency=1.0)
    reg.failure("w", "boom")
    assert reg.score("w") == -1.0


def test_score_penalized_by_consecutive_verify_failures(reg):
    reg.register("a")
    reg.register("b")
    reg.success("a", latency=1.0)
    reg.success("b", latency=1.0)
    clean = reg.score("a")
    reg.verify_failure("b", "bad")
    assert reg.score("b") < clean


def test_score_complexity_mismatch_loses_to_match(reg):
    reg.register("hi")
    reg.register("lo")
    reg.success("hi", latency=2.0)
    reg.success("lo", latency=2.0)
    reg.state("hi").complexity = 5
    assert reg.score("hi", task_complexity=5, worker_complexity=5) >= \
        reg.score("lo", task_complexity=5, worker_complexity=1)


# --------------------------------------------------------------------------
# 7. Персистентность: битое/отсутствующее state-файл, ошибки записи
# --------------------------------------------------------------------------
def test_missing_state_file_is_not_an_error(tmp_path, clock):
    r = HealthRegistry(state_file=tmp_path / "nope" / "ws.json")
    assert r.states == {}
    assert r.available("never-seen") is True  # state() создаёт запись


def test_corrupt_json_state_file_ignored(tmp_path, clock):
    f = tmp_path / "ws.json"
    f.write_text("{not json at all", encoding="utf-8")
    r = HealthRegistry(state_file=f)
    assert r.states == {}


def test_empty_json_object_state_file(tmp_path, clock):
    f = tmp_path / "ws.json"
    f.write_text("{}", encoding="utf-8")
    r = HealthRegistry(state_file=f)
    assert r.states == {}
    assert r.available("w") is True


def test_load_state_ignores_null_field_values(tmp_path, clock):
    f = tmp_path / "ws.json"
    f.write_text(json.dumps({"w": {"status": "ERROR", "consecutive_failures": None,
                                   "cooldown_until": None}}), encoding="utf-8")
    r = HealthRegistry(state_file=f)
    st = r.state("w")
    assert st.status == "ERROR"
    assert st.consecutive_failures == 0  # None не перетирает дефолт в null


def test_save_state_swallows_os_error(tmp_path, monkeypatch, clock):
    r = HealthRegistry(state_file=tmp_path / "ws.json")
    monkeypatch.setattr(Path, "write_text", _raise_os_error)
    r.register("w")
    r.failure("w", "boom")  # не должно бросать
    assert r.state("w").consecutive_failures == 1


def test_save_state_is_atomic_no_tmp_left_behind(tmp_path, clock):
    r = HealthRegistry(state_file=tmp_path / "ws.json")
    r.register("w")
    r.success("w", latency=1.0)
    leftovers = list(tmp_path.glob("*.tmp"))
    assert leftovers == [], f"остались .tmp: {leftovers}"
    assert (tmp_path / "ws.json").is_file()


def test_state_dict_excludes_transient_running_count(tmp_path, clock):
    r = HealthRegistry(state_file=tmp_path / "ws.json")
    r.register("w")
    r.begin_task("w")
    assert "running_count" not in r.snapshot()["w"]


# --------------------------------------------------------------------------
# 8. UI-facing снапшоты
# --------------------------------------------------------------------------
def test_effective_status_busy_wins_over_cooldown(reg, clock):
    reg.register("w")
    reg.failure("w", "boom")
    reg.state("w").running_count = 1
    assert reg.effective_status("w") == "BUSY"


def test_effective_status_billing_and_circuit_not_masked_by_cooldown(reg, clock):
    reg.register("b")
    reg.register("c")
    reg.failure("b", "402 payment required")
    reg.state("c").status = "CIRCUIT"
    reg.state("c").cooldown_until = clock.now + 100
    assert reg.effective_status("b") == "BILLING"
    assert reg.effective_status("c") == "CIRCUIT"


def test_effective_status_cooldown_checked_before_rate_limit(reg, clock):
    """cooldown_until > now имеет приоритет над rate_limit_until > now.

    Порядок в effective_status: BUSY -> CIRCUIT/BILLING -> cooldown ->
    rate limit -> DEGRADED. При равных дедлайнах UI видит COOLDOWN.
    """
    reg.register("w")
    reg.failure("w", "429 too many requests")
    st = reg.state("w")
    assert st.rate_limit_until == st.cooldown_until  # обе ветки дают одну задержку
    assert reg.effective_status("w") == "COOLDOWN"

    clock.advance(600.1)  # оба дедлайна истекли
    assert reg.state("w").rate_limit_until <= clock.now
    assert reg.effective_status("w") == "RATE_LIMITED"


def test_effective_status_degraded_by_series_even_without_status(reg, clock):
    reg.register("w")
    reg.state("w").consecutive_verify_failures = 3
    assert reg.effective_status("w") == "DEGRADED"


def test_operator_snapshot_unknown_worker_reported_as_available(reg, clock):
    """operator_snapshot обходит self.states, поэтому нужно state(name)."""
    reg.register("w")
    assert reg.operator_snapshot() == []  # register() не создаёт state
    reg.state("w")
    row = next(r for r in reg.operator_snapshot() if r["name"] == "w")
    assert row["status"] == "AVAILABLE"
    assert row["success_rate"] == 0.5  # нет данных -> нейтральные 0.5


def test_operator_snapshot_reports_remaining_cooldown_seconds(reg, clock):
    """Чистый COOLDOWN показывается только для нейтральных статусов.

    Для ERROR/TIMEOUT/BILLING/LOOP/DEGRADED статус не переписывается в
    COOLDOWN (он информативнее), но detail с остатком секунд остаётся.
    """
    reg.register("w")
    reg.state("w")  # нейтральный UNKNOWN
    reg.state("w").cooldown_until = clock.now + 50
    row = next(r for r in reg.operator_snapshot() if r["name"] == "w")
    assert row["status"] == "COOLDOWN"
    assert "50" in row["detail"]

    reg.register("e")
    reg.failure("e", "boom")
    clock.advance(10)
    row_e = next(r for r in reg.operator_snapshot() if r["name"] == "e")
    assert row_e["status"] == "ERROR", "ERROR не должен маскироваться в COOLDOWN"
    assert "50" in row_e["detail"]


def test_dashboard_rows_score_is_minus_one_when_unavailable(reg, clock):
    reg.register("w")
    reg.failure("w", "boom")
    row = next(r for r in reg.dashboard_rows() if r["worker"] == "w")
    assert row["score"] == -1.0
    assert row["cooldown_sec"] == 60


def test_dashboard_rows_covers_unregistered_names(tmp_path, clock):
    r = HealthRegistry(state_file=tmp_path / "ws.json")
    r.register("w", max_parallel=4)
    rows = r.dashboard_rows()
    assert any(row["worker"] == "w" and row["max_parallel"] == 4 for row in rows)


def test_worker_state_success_rate_zero_attempts_is_neutral():
    """Нет ни одного завершения -> 0.5, а не ZeroDivisionError."""
    assert WorkerState().success_rate == 0.5
    assert WorkerState(success_count=0, fail_count=0).success_rate == 0.5
    assert WorkerState(success_count=3, fail_count=1).success_rate == 0.75


def _no_budget_registry(tmp_path, *, base_cooldown=60, circuit_limit=3):
    """HealthRegistry с заглушкой бюджета (GLOBAL_BUDGET глобален и лимитен)."""
    r = HealthRegistry(base_cooldown=base_cooldown, circuit_limit=circuit_limit,
                       state_file=tmp_path / "ws.json")
    r.budget = type("NoBudget", (), {
        "can_use": lambda self, name: True,
        "record": lambda self, name, tokens=0: None,
        "remaining": lambda self, name: {},
        "snapshot": lambda self: {},
    })()
    return r


def _raise_os_error(*args, **kwargs):
    raise OSError(13, "Permission denied")
