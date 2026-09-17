# -*- coding: utf-8 -*-
from app.facade import AppFacade, get_app

def test_facade_empty_messages():
    f = AppFacade()
    assert f.empty_message("queue")
    assert f.empty_message("history")

def test_get_app_singleton():
    a = get_app()
    b = get_app()
    assert a is b

def test_facade_soft_fail_health(tmp_path):
    f = AppFacade(tmp_path)
    text = f.health_text()
    assert isinstance(text, str)
