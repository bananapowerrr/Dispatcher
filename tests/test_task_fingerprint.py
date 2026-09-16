# -*- coding: utf-8 -*-
"""Official task_fingerprint stability (P1 identity)."""
from __future__ import annotations

from core.dedupe import task_fingerprint, normalize_message
from core.tasks import Task


def test_normalize_message_collapses_ws():
    assert normalize_message("  a\n  b\t ") == "a b"


def test_fingerprint_stable_across_noise_meta():
    a = {
        "project": "/p",
        "message": "fix code",
        "files": ["b.py", "a.py"],
        "verify": [],
        "run": [],
        "executor": "",
        "channel": "desktop",
        "metadata": {"claimed_at": "2020-01-01", "phase": "worker"},
    }
    b = dict(a)
    b["metadata"] = {"last_heartbeat": 1.23, "reclaim_reason": "stuck", "phase": "verify"}
    b["id"] = "other-id"
    b["status"] = "CLAIMED"
    b["attempts"] = 9
    assert task_fingerprint(a) == task_fingerprint(b)


def test_fingerprint_changes_on_message():
    a = {"project": "/p", "message": "one", "files": [], "channel": "desktop", "metadata": {}}
    b = {"project": "/p", "message": "two", "files": [], "channel": "desktop", "metadata": {}}
    assert task_fingerprint(a) != task_fingerprint(b)


def test_fingerprint_message_whitespace_invariant():
    a = {"project": "/p", "message": "fix   code", "files": ["x.py"], "channel": "desktop", "metadata": {}}
    b = {"project": "/p", "message": "fix\ncode", "files": ["x.py"], "channel": "desktop", "metadata": {}}
    assert task_fingerprint(a) == task_fingerprint(b)


def test_fingerprint_files_order_invariant():
    a = {"project": "/p", "message": "m", "files": ["b.py", "a.py"], "channel": "desktop", "metadata": {}}
    b = {"project": "/p", "message": "m", "files": ["a.py", "b.py"], "channel": "desktop", "metadata": {}}
    assert task_fingerprint(a) == task_fingerprint(b)


def test_task_bump_attempt():
    t = Task(id="t1", project="/p", message="m")
    assert t.attempts == 0
    n = t.bump_attempt(error="boom", max_attempts=3)
    assert n == 1
    assert t.metadata.get("attempts") == 1
    assert t.metadata.get("last_error") == "boom"
    assert not t.exhausted(3)
    t.bump_attempt()
    t.bump_attempt()
    assert t.exhausted(3)
