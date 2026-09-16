# -*- coding: utf-8 -*-
"""FC-37C Session bootstrap tests."""
from __future__ import annotations

import os
from pathlib import Path

from intelligence.session_bootstrap import bootstrap_banner, bootstrap_session


def _proj(tmp: Path) -> Path:
    (tmp / "main.py").write_text("print(1)\n", encoding="utf-8")
    return tmp


def test_bootstrap_runs(tmp_path: Path):
    r = bootstrap_session(_proj(tmp_path), use_cache=False, use_index=False)
    assert not r.skipped
    assert r.kind or r.analysis_summary
    assert r.duration_ms >= 0
    assert "происходит" in r.banner.lower() or r.banner


def test_cache_hit(tmp_path: Path):
    root = _proj(tmp_path)
    r1 = bootstrap_session(root, use_cache=True, cache_ttl_sec=3600, use_index=False)
    r2 = bootstrap_session(root, use_cache=True, cache_ttl_sec=3600, use_index=False)
    assert r2.cached
    assert r2.banner == r1.banner


def test_force_refresh(tmp_path: Path):
    root = _proj(tmp_path)
    bootstrap_session(root, use_cache=True, use_index=False)
    r = bootstrap_session(root, force=True, use_cache=True, use_index=False)
    assert not r.cached


def test_env_disable(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AGENTBUS_SESSION_SCAN", "0")
    r = bootstrap_session(_proj(tmp_path), use_index=False)
    assert r.skipped


def test_banner_helper(tmp_path: Path):
    text = bootstrap_banner(_proj(tmp_path), use_cache=False)
    assert isinstance(text, str)
    assert text


def test_missing_dir(tmp_path: Path):
    r = bootstrap_session(tmp_path / "nope", use_cache=False)
    assert r.skipped
