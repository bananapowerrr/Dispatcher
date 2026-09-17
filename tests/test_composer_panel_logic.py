# -*- coding: utf-8 -*-
from app.task_composer import compose_task, validate_task_dict, format_composer_preview

def test_compose_and_validate():
    t = compose_task(message="add docstring", project="/tmp/p", files=["a.py"], priority=2)
    assert t["message"] == "add docstring"
    assert t["files"] == ["a.py"]
    assert validate_task_dict(t) == []
    prev = format_composer_preview(t)
    assert "add docstring" in prev
    assert "a.py" in prev

def test_compose_requires_message():
    try:
        compose_task(message="  ")
        assert False
    except ValueError:
        pass

def test_wizard_briefing_import():
    from ui.setup_wizard import post_wizard_briefing
    assert callable(post_wizard_briefing)

def test_facade_still_ok():
    from app.facade import AppFacade
    assert AppFacade().empty_message("queue")
