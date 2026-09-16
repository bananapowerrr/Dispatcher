from budget import Budget


def test_daily_limit_counts_calls_and_remaining():
    b = Budget()
    b.calls.clear()
    for _ in range(50):
        assert b.can_use("aider_or_free")
        b.record("aider_or_free")
    assert b.remaining("aider_or_free")["per_day"] == 0
    assert not b.can_use("aider_or_free")


def test_together_monthly_token_limit():
    b = Budget()
    b.calls.clear()
    b.record("aider_together_big", tokens=999_999)
    assert b.remaining("aider_together_big")["per_month_tokens"] == 1
    b.record("aider_together_big", tokens=1)
    assert b.remaining("aider_together_big")["per_month_tokens"] == 0
    assert not b.can_use("aider_together_big")


def test_unlimited_worker_has_no_budget_limit():
    b = Budget()
    b.record("aider_local", tokens=10_000_000)
    assert b.can_use("aider_local")
    assert b.remaining("aider_local") == {"per_day": None, "per_month_tokens": None}
