# -*- coding: utf-8 -*-

def test_timeout_allows():
    from core.worker_fallback import allow_worker_fallback
    assert allow_worker_fallback(kind="worker_timeout") is True
    assert allow_worker_fallback(status="timeout") is True


def test_unavailable_allows():
    from core.worker_fallback import allow_worker_fallback
    assert allow_worker_fallback(kind="worker_unavailable") is True
    assert allow_worker_fallback(status="unavailable") is True


def test_verification_denies():
    from core.worker_fallback import allow_worker_fallback
    assert allow_worker_fallback(kind="verification_failed") is False


def test_invalid_output_denies():
    from core.worker_fallback import allow_worker_fallback
    assert allow_worker_fallback(status="invalid_output") is False
    assert allow_worker_fallback(kind="worker_loop") is False


def test_auth_denies():
    from core.worker_fallback import allow_worker_fallback
    assert allow_worker_fallback(kind="worker_auth") is False


def test_recovery_decision_override():
    from core.worker_fallback import allow_worker_fallback
    assert allow_worker_fallback(
        kind="worker_timeout",
        recovery_decision={"allow_fallback": False},
    ) is False
    assert allow_worker_fallback(
        kind="verification_failed",
        recovery_decision={"allow_fallback": True},
    ) is True


def test_filter_pool_empty_when_denied():
    from core.worker_fallback import filter_fallback_pool
    class W:
        def __init__(self, name):
            self.name = name
            self.provider = "ollama"
            self.priority = 1
            self.tier = 1
    pool = filter_fallback_pool(
        [W("a"), W("b")],
        tried=["a"],
        kind="verification_failed",
    )
    assert pool == []


def test_filter_pool_allows_timeout():
    from core.worker_fallback import filter_fallback_pool
    class W:
        def __init__(self, name, provider="ollama"):
            self.name = name
            self.provider = provider
            self.priority = 1
            self.tier = 1
    pool = filter_fallback_pool(
        [W("a"), W("b")],
        tried=["a"],
        kind="worker_timeout",
    )
    assert any(w.name == "b" for w in pool)


def test_rp_llm_has_dev004_gate():
    from pathlib import Path
    src = Path("/home/workdir/artifacts/src/core/rp_llm.py").read_text(encoding="utf-8")
    assert "allow_worker_fallback" in src
