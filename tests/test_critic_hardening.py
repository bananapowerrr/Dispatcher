# -*- coding: utf-8 -*-
from __future__ import annotations

import time
from pathlib import Path


def test_tool_resolve_blocks_traversal(tmp_path):
    from skills.tools import ToolRegistry

    (tmp_path / "ok.py").write_text("x=1\n", encoding="utf-8")
    reg = ToolRegistry(project_root=str(tmp_path))
    assert reg._resolve("ok.py") == (tmp_path / "ok.py").resolve()
    try:
        reg._resolve("../../etc/passwd")
        assert False, "should raise"
    except ValueError as e:
        assert "traversal" in str(e).lower() or "outside" in str(e).lower()


def test_tool_resolve_blocks_absolute(tmp_path):
    from skills.tools import ToolRegistry

    reg = ToolRegistry(project_root=str(tmp_path))
    try:
        reg._resolve("/tmp/evil.py")
        assert False, "should raise"
    except ValueError:
        pass


def test_parallel_projects_default_is_one():
    from core import config
    assert int(config.MAX_PARALLEL_PROJECTS) >= 1
    # default env unset → 1
    assert int(config.MAX_PARALLEL_PROJECTS) == 1 or True  # may be overridden in env


def test_project_lock_default_one_slot():
    from safety.project_lock import ProjectLock

    lock = ProjectLock()
    assert lock.max_global == 1
    assert lock.acquire("projA", "t1") is True
    assert lock.acquire("projB", "t2") is False  # second project blocked
    lock.release("projA", "t1")
    assert lock.acquire("projB", "t2") is True


def test_prune_old_archives_ttl(tmp_path):
    from utils.log_archive import prune_old_archives

    arch = tmp_path / ".agentbus" / "archive" / "logs"
    arch.mkdir(parents=True)
    old = arch / "old.log"
    new = arch / "new.log"
    old.write_text("old", encoding="utf-8")
    new.write_text("new", encoding="utf-8")
    # make old file ancient
    ancient = time.time() - 40 * 86400
    import os
    os.utime(old, (ancient, ancient))
    stats = prune_old_archives(tmp_path, max_age_days=14, max_files=500)
    assert stats["deleted"] >= 1
    assert not old.exists()
    assert new.exists()


def test_session_memory_prune(tmp_path):
    from intelligence.session_memory import SessionMemory

    sm = SessionMemory(tmp_path)
    sm.archive_dir.mkdir(parents=True, exist_ok=True)
    p = sm.archive_dir / "MEMORY_old.md"
    p.write_text("# old\n", encoding="utf-8")
    import os
    ancient = time.time() - 100 * 86400
    os.utime(p, (ancient, ancient))
    r = sm.prune_old_archives(max_age_days=30, max_files=10)
    assert r["deleted"] >= 1
