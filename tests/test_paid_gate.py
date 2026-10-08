# -*- coding: utf-8 -*-
"""Платный шлюз: AGENTBUS_ALLOW_PAID=0 обязан блокировать облака.

Контекст: ALLOW_PAID был заведён и печатался, но не проверялся — после починки
preflight (c-long-040046) роутер начал выбирать aider_openrouter/huggingface/
together, и они реально тратили деньги. Политика программы — «абсолютно
бесплатные ресурсы», поэтому единственная платная валюта здесь — локальный
runtime.

Также проверяем, что локальный CLI (opencode, provider: zen — его нет в
providers.yaml) не выпадает из планирования вместе с облаками.
"""
from __future__ import annotations

import pytest

from core.paid_gate import (
    is_paid_provider,
    is_paid_worker,
    describe_worker,
    LOCAL_PROVIDER_IDS,
)
from core.router import select_executor
from core.workers import Worker
from safety.health import HealthRegistry


@pytest.fixture
def health(tmp_path):
    return HealthRegistry(state_file=tmp_path / "ws.json")


def _w(name, provider="ollama", *, enabled=True, billing="", caps=(), priority=10,
       harness="aider"):
    return Worker(name=name, command=("{aider}", "{message}"), harness=harness,
                  provider=provider, model="m", complexity=2, quality=1.0,
                  enabled=enabled, priority=priority, billing=billing,
                  capabilities=tuple(caps))


TASK_FILE = {"id": "t1", "message": "create file x.py", "files": ["x.py"]}
TASK_PLAN = {"id": "t2", "message": "спланировать архитектуру"}


# --- paid_gate: классификация провайдеров -------------------------------

def test_local_providers_are_free():
    for pid in ("ollama", "lmstudio", "local", ""):
        assert is_paid_provider(pid) is False, pid


def test_cloud_providers_are_paid_despite_free_tier_label():
    # providers.yaml помечает облака billing: free (free-тир), но по политике
    # программы это не бесплатно.
    assert is_paid_provider("openrouter") is True
    assert is_paid_provider("together") is True
    assert is_paid_provider("huggingface") is True
    assert is_paid_provider("siliconflow") is True


def test_explicit_billing_labels_win():
    assert is_paid_provider("ollama", billing="paid") is True
    assert is_paid_provider("openrouter", billing="local") is False


def test_unknown_remote_provider_defaults_to_paid():
    # Консервативный дефолт: новое облако не должно молча начать стоить денег.
    # Проверка обязана ловить и переименование облака, и опечатку в id.
    assert is_paid_provider("some_new_cloud") is True
    assert is_paid_provider("openrouter_typo") is True
    assert is_paid_provider("openruter") is True


def test_unregistered_provider_is_paid_even_for_aider():
    # aider с незнакомым провайдером — это удалённый API, а не локальный CLI.
    assert is_paid_provider("mystery_cloud", harness="aider") is True


def test_local_cli_harness_is_not_paid():
    # opencode: provider zen отсутствует в providers.yaml, платить ему нечем.
    assert is_paid_provider("zen", harness="opencode") is False
    # тот же провайдер, но с обычным харнессом — уже не локальный CLI
    assert is_paid_provider("zen", harness="aider") is True
    assert "zen" not in LOCAL_PROVIDER_IDS


def test_worker_billing_override_wins_over_provider():
    assert is_paid_worker(_w("x", "openrouter", billing="free")) is False
    assert is_paid_worker(_w("x", "ollama", billing="paid")) is True
    assert describe_worker(_w("x", "together")) == "PAID"
    assert describe_worker(_w("x", "ollama")) == "FREE"


def test_real_opencode_worker_is_free():
    """Стоп-регрессия: настоящий opencode (harness=opencode) не платный."""
    assert describe_worker(
        _w("opencode", "zen", harness="opencode", caps=("plan",))
    ) == "FREE"


# --- select_executor: жёсткая блокировка ---------------------------------

def test_paid_workers_not_selected_when_paid_forbidden(health):
    paid = [_w("aider_openrouter", "openrouter", priority=1),
            _w("aider_together", "together", priority=2)]
    for w in paid:
        health.register(w.name)
    # priority меньше = выше приоритет в роутере, поэтому выбрался бы openrouter
    assert select_executor(paid, health, TASK_FILE, allow_paid=False) is None


def test_local_worker_wins_and_paid_is_skipped(health):
    workers = [_w("aider_local", "ollama", priority=10),
               _w("aider_openrouter", "openrouter", priority=1)]
    for w in workers:
        health.register(w.name)
    from core import router
    chosen = select_executor(workers, health, TASK_FILE, allow_paid=False)
    assert chosen is not None and chosen.name == "aider_local"
    assert router.LAST_SKIPS["aider_openrouter"] == "paid_disallowed[ALLOW_PAID=0]"


def test_paid_allowed_explicitly_reaches_cloud(health):
    workers = [_w("aider_openrouter", "openrouter", priority=1)]
    for w in workers:
        health.register(w.name)
    chosen = select_executor(workers, health, TASK_FILE, allow_paid=True)
    assert chosen is not None and chosen.name == "aider_openrouter"


def test_paid_gate_defaults_to_deny_without_explicit_flag(health, monkeypatch):
    """Без явного allow_paid поведение берётся из конфига и по умолчанию — deny."""
    import core.config as cfg
    monkeypatch.setattr(cfg, "ALLOW_PAID", False, raising=False)
    workers = [_w("aider_together", "together", priority=1)]
    for w in workers:
        health.register(w.name)
    assert select_executor(workers, health, TASK_FILE) is None


def test_plan_only_worker_survives_paid_gate(health):
    """Планирование не должно ломаться: opencode локальный, хоть и plan-only."""
    workers = [_w("aider_local", "ollama", enabled=False),
               _w("opencode", "zen", harness="opencode", caps=("plan",))]
    for w in workers:
        health.register(w.name)
    chosen = select_executor(workers, health, TASK_PLAN, requested="opencode",
                             allow_paid=False)
    assert chosen is not None and chosen.name == "opencode"


def test_no_paid_charge_when_only_paid_pool_left(health):
    """Ключевой сценарий из приёмки: локальный выключен → DEFERRED, не облако."""
    workers = [_w("aider_local", "ollama", enabled=False),
               _w("aider_huggingface", "huggingface"),
               _w("aider_openrouter", "openrouter")]
    for w in workers:
        health.register(w.name)
    from core import router
    assert select_executor(workers, health, TASK_FILE, allow_paid=False) is None
    assert router.LAST_SKIPS["aider_huggingface"].startswith("paid_disallowed")
    assert router.LAST_SKIPS["aider_openrouter"].startswith("paid_disallowed")
