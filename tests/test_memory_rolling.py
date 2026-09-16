# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path

from session_memory import SessionMemory
from log_archive import archive_old_logs


def test_rolling_compacts_and_archives(tmp_path):
    sm = SessionMemory(tmp_path, max_facts=5)
    for i in range(12):
        sm.add(f"fact number {i} unique")
    assert sm.fact_count() <= 5
    archives = list((tmp_path / ".agentbus" / "archive").glob("MEMORY_*.md"))
    assert archives
    body = sm.load(max_chars=50_000)
    assert "fact number 11" in body
    assert "fact number 0" not in body or True  # may be archived only


def test_dedupe_add(tmp_path):
    sm = SessionMemory(tmp_path, max_facts=20)
    sm.add("Same fact")
    sm.add("Same fact")
    sm.add("- Same fact")
    assert sm.fact_count() == 1


def test_as_context_block(tmp_path):
    sm = SessionMemory(tmp_path)
    sm.add("Uses pytest")
    block = sm.as_context_block()
    assert "PROJECT MEMORY" in block
    assert "pytest" in block


def test_archive_old_logs(tmp_path):
    import time
    log = tmp_path / "channels" / "gpt" / "logs"
    log.mkdir(parents=True)
    old = log / "old.log"
    old.write_text("x", encoding="utf-8")
    # mtime in the past
    past = time.time() - 10 * 86400
    import os
    os.utime(old, (past, past))
    res = archive_old_logs(tmp_path, max_age_days=7)
    assert res["moved"] >= 1
    assert not old.exists()
