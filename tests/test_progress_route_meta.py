def test_progress_includes_route_preview_worker():
    from ui.chat_task_bridge import format_progress_event

    row = {
        "status": "processing",
        "metadata": {
            "route_preview": {"worker": "aider_local", "advisory": True},
            "phase": "PROCESSING",
        },
    }
    out = format_progress_event(row)
    assert "aider_local" in out["chat"] or "aider_local" in out["phase"]


def test_doctor_route_snippet():
    from app.product_surface import doctor_route_snippet

    s = doctor_route_snippet("create file")
    assert len(s) > 5
