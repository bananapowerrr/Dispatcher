# -*- coding: utf-8 -*-
from slash_commands import handle_slash, COMMANDS


def test_help_lists_new_commands():
    msg = handle_slash("/help", {})
    assert msg and "/status" in msg
    assert "/features" in msg
    assert "/skills" in msg


def test_features_command():
    msg = handle_slash("/features", {})
    assert msg and ("ON" in msg or "on" in msg.lower() or "features" in msg.lower())


def test_status_command():
    msg = handle_slash("/status", {})
    assert msg
    assert "unavailable" not in msg or "tasks" in msg or "features" in msg


def test_skills_command():
    msg = handle_slash("/skills", {})
    assert msg
    assert msg.startswith("skills:")


def test_unknown_command():
    msg = handle_slash("/nope_xyz", {})
    assert "Неизвестная" in msg or "help" in msg.lower()


def test_commands_registered():
    for cmd in ("/status", "/features", "/metrics", "/skills", "/workers", "/cost"):
        assert cmd in COMMANDS
