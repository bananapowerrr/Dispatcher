# -*- coding: utf-8 -*-

def test_prioritize_message_hits_first():
    from intelligence.context_budget import prioritize_files
    files = [
        "docs/README.md",
        "ui/chat_panel.py",
        "src/core/executor.py",
        "tests/test_executor.py",
    ]
    out = prioritize_files(files, message="fix executor timeout", max_files=3)
    assert "src/core/executor.py" in out
    assert out[0].endswith("executor.py") or "executor" in out[0]


def test_docs_ranked_lower():
    from intelligence.context_budget import prioritize_files
    files = ["docs/guide.md", "src/core/timeout_policy.py"]
    out = prioritize_files(files, message="timeout policy", max_files=2)
    assert out[0].endswith("timeout_policy.py")


def test_assemble_includes_audit():
    from intelligence.context_budget import assemble_worker_message
    out = assemble_worker_message(
        user_message="fix executor",
        files=["src/core/executor.py", "docs/README.md", "ui/chat_panel.py"],
        previous_failure="timeout on line 10",
        total_chars=8000,
        max_files=2,
    )
    assert "context_audit" in out
    assert out["context_audit"]["selected_n"] <= 2
    assert out["context_audit"]["has_previous_failure"] is True
    assert "USER REQUEST" in out["message"]
    assert "Previous failure" in out["message"]


def test_user_request_alias():
    from intelligence.context_budget import assemble_worker_message
    out = assemble_worker_message(user_request="hello alias", total_chars=3000)
    assert "hello alias" in out["message"]


def test_truncation_audit():
    from intelligence.context_budget import assemble_worker_message
    out = assemble_worker_message(
        user_message="x",
        file_excerpts="E" * 50000,
        total_chars=2000,
    )
    assert out["chars"] <= 2000
    assert out["context_audit"]["chars"] <= 2000
