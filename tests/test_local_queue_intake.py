# -*- coding: utf-8 -*-
"""LocalQueue must reject unsafe paths via intake (fail-closed)."""
from __future__ import annotations

import pytest


def test_put_accepts_safe(tmp_path):
    from core.local_queue import LocalQueue

    q = LocalQueue(spill_dir=tmp_path / "spill")
    tid = q.put({"message": "format a.py", "files": ["src/a.py"]})
    assert tid
    task = q.claim()
    assert task is not None
    assert task["message"].startswith("format")
    assert task["metadata"].get("intake_source") == "desktop_queue" or task["metadata"].get("source")


def test_put_rejects_traversal(tmp_path):
    from core.local_queue import LocalQueue

    q = LocalQueue(spill_dir=tmp_path / "spill")
    with pytest.raises(ValueError, match="reject"):
        q.put({"message": "leak", "files": ["../../etc/passwd"]})
    assert q.size() == 0


def test_enqueue_rejects_traversal(tmp_path, monkeypatch):
    from core import local_queue as lq
    from core.local_queue import LocalQueue, enqueue_desktop_task

    lq._GLOBAL = LocalQueue(spill_dir=tmp_path / "spill")
    with pytest.raises(ValueError, match="reject"):
        enqueue_desktop_task("x", files=["../secret"], root=tmp_path)
