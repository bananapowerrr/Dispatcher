# -*- coding: utf-8 -*-

def test_done_story_includes_model_and_verify():
    from app.product_surface import format_done_story

    text = format_done_story({
        "id": "abc123456789",
        "metadata": {
            "worker": "aider_local",
            "model": "qwen2.5-coder:7b",
            "context_audit": {"selected_n": 3, "chars": 4000},
        },
        "result": {
            "worker": "aider_local",
            "changed_files": ["src/core/executor.py"],
            "verification": {"ok": True, "passed": True},
            "verified": True,
        },
    })
    assert "worker: aider_local" in text
    assert "model: qwen2.5-coder" in text
    assert "executor.py" in text
    assert "verification passed" in text
    assert "context files: 3" in text
