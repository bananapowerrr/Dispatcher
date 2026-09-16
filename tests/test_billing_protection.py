from __future__ import annotations

import time

from executor import ExecutionResult, is_billing_error
from health import HealthRegistry


def test_billing_markers_are_detected_case_insensitively():
    markers = [
        "insufficient credits",
        "billing required",
        "payment required",
        "quota exceeded",
        "402 Payment Required",
        "balance insufficient",
        "no credits available",
    ]
    for marker in markers:
        assert is_billing_error(f"Provider error: {marker}")


def test_execution_result_carries_billing_error_flag():
    result = ExecutionResult(False, stderr="402 Payment Required", billing_error=True)
    assert result.billing_error is True


def test_billing_failure_gets_24h_cooldown(tmp_path):
    health = HealthRegistry(state_file=tmp_path / "workers.json")
    health.register("aider_sf_big", 1)

    before = time.monotonic()
    health.failure("aider_sf_big", "402 Payment Required: balance insufficient")
    state = health.state("aider_sf_big")

    assert state.status == "BILLING"
    assert state.cooldown_until >= before + 86390
    assert health.available("aider_sf_big") is False


def test_billing_flag_can_trigger_cooldown_without_marker_text(tmp_path):
    health = HealthRegistry(state_file=tmp_path / "workers.json")
    health.register("provider", 1)

    health.failure("provider", "provider rejected request", billing_error=True)
    state = health.state("provider")

    assert state.status == "BILLING"
    assert state.cooldown_until > time.monotonic() + 86300
    assert health.available("provider") is False
