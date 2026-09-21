# -*- coding: utf-8 -*-

def test_plan_allocates():
    from intelligence.context_budget import build_context_budget_plan

    p = build_context_budget_plan(total_chars=10000, has_failure=True, n_files=5)
    assert p["user"] >= 400
    assert p["failure"] > 0
    assert p["excerpts"] > 0
    assert sum(v for k, v in p.items() if k != "total") <= p["total"] + 500


def test_assemble_truncates():
    from intelligence.context_budget import assemble_worker_message

    big = "x" * 50000
    out = assemble_worker_message(
        user_message="fix bug",
        files=[f"a{i}.py" for i in range(20)],
        constraints=["max files small"],
        previous_failure=big,
        file_excerpts=big,
        total_chars=8000,
    )
    assert out["chars"] <= 8000
    assert "USER REQUEST" in out["message"]
    assert out["truncated"] or out["chars"] <= 8000


def test_previous_failure_priority():
    from intelligence.context_budget import assemble_worker_message

    out = assemble_worker_message(
        user_message="retry",
        previous_failure="pytest failed on line 10",
        total_chars=5000,
    )
    assert "Previous failure" in out["message"]
    assert "pytest failed" in out["message"]


def test_verification_distinct_from_empty():
    from intelligence.context_budget import format_constraints
    assert format_constraints([]) == ""
    assert "Constraints" in format_constraints(["no cloud"])
