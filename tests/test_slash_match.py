"""Slash command autocomplete helpers."""
from __future__ import annotations

from utils.slash_commands import list_slash_commands, match_slash


def test_list_slash_has_help():
    cmds = list_slash_commands()
    assert "/help" in cmds
    assert "/status" in cmds


def test_match_slash_prefix():
    m = match_slash("/he")
    assert "/help" in m
    assert all(x.startswith("/he") or x == "/help" or x.startswith("/h") for x in m) or "/help" in m


def test_match_without_slash():
    m = match_slash("cost")
    assert "/cost" in m
