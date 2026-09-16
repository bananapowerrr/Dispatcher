# -*- coding: utf-8 -*-
"""solution_cache: git HEAD in key, TTL, LRU."""
from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path
from types import SimpleNamespace

import pytest


def _git_init_with_commit(repo: Path) -> str:
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    (repo / "a.py").write_text("x = 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "a.py"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    return head


def test_make_key_includes_git_head():
    from intelligence.solution_cache import SolutionCache

    k1 = SolutionCache.make_key(message="fix", files=["a.py"], git_head="aaa", git_dirty=False)
    k2 = SolutionCache.make_key(message="fix", files=["a.py"], git_head="bbb", git_dirty=False)
    k3 = SolutionCache.make_key(message="fix", files=["a.py"], git_head="aaa", git_dirty=True)
    assert k1 != k2
    assert k1 != k3


def test_put_get_hit_same_head(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AGENTBUS_CACHE_GIT", "1")
    from intelligence.solution_cache import SolutionCache

    repo = tmp_path / "repo"
    repo.mkdir()
    head = _git_init_with_commit(repo)
    cache = SolutionCache(cache_path=tmp_path / "c.json", max_entries=50, ttl_seconds=3600)
    task = SimpleNamespace(
        message="fix task",
        files=["a.py"],
        project="demo",
        verify=[],
    )
    cache.put(task, {"method": "llm", "worker": "w", "summary": "ok"}, project_root=repo)
    hit = cache.get(task, project_root=repo)
    assert hit is not None
    assert hit.get("git_head", "").startswith(head[:7]) or hit.get("git_head") == head


def test_miss_after_new_commit(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AGENTBUS_CACHE_GIT", "1")
    from intelligence.solution_cache import SolutionCache

    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init_with_commit(repo)
    cache = SolutionCache(cache_path=tmp_path / "c.json")
    task = SimpleNamespace(message="edit a", files=["a.py"], project="demo", verify=[])
    cache.put(task, {"method": "llm", "summary": "v1"}, project_root=repo)
    assert cache.get(task, project_root=repo) is not None

    (repo / "a.py").write_text("x = 2\n", encoding="utf-8")
    subprocess.run(["git", "add", "a.py"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "second"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    # new HEAD → different key → miss
    assert cache.get(task, project_root=repo) is None


def test_dirty_tree_different_key(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AGENTBUS_CACHE_GIT", "1")
    from intelligence.solution_cache import SolutionCache, git_repo_state

    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init_with_commit(repo)
    head, dirty = git_repo_state(repo)
    assert head and not dirty

    (repo / "a.py").write_text("x = 99\n", encoding="utf-8")  # unstaged
    head2, dirty2 = git_repo_state(repo)
    assert dirty2 is True
    assert head2 == head

    from intelligence.solution_cache import SolutionCache as SC
    k_clean = SC.make_key(message="m", files=["a.py"], git_head=head, git_dirty=False)
    k_dirty = SC.make_key(message="m", files=["a.py"], git_head=head2, git_dirty=True)
    assert k_clean != k_dirty


def test_ttl_expires(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AGENTBUS_CACHE_GIT", "0")
    from intelligence.solution_cache import SolutionCache

    cache = SolutionCache(cache_path=tmp_path / "c.json", ttl_seconds=0.2)
    task = SimpleNamespace(message="ttl", files=[], project="", verify=[])
    cache.put(task, {"method": "skill", "summary": "s"}, project_root=None)
    assert cache.get(task, project_root=None) is not None
    time.sleep(0.35)
    assert cache.get(task, project_root=None) is None


def test_lru_evicts_oldest(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AGENTBUS_CACHE_GIT", "0")
    from intelligence.solution_cache import SolutionCache

    cache = SolutionCache(cache_path=tmp_path / "c.json", max_entries=2, ttl_seconds=0)
    for i in range(3):
        t = SimpleNamespace(message=f"msg-{i}", files=[], project="", verify=[])
        cache.put(t, {"method": "llm", "summary": str(i)}, project_root=None)
        time.sleep(0.02)
    assert cache.stats()["count"] == 2
    # oldest msg-0 should be gone
    t0 = SimpleNamespace(message="msg-0", files=[], project="", verify=[])
    t2 = SimpleNamespace(message="msg-2", files=[], project="", verify=[])
    assert cache.get(t0, project_root=None) is None
    assert cache.get(t2, project_root=None) is not None
