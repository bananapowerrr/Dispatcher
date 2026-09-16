# -*- coding: utf-8 -*-
"""Attachments pipeline + feature flag save/load."""
from __future__ import annotations

from pathlib import Path

import pytest


def test_materialize_text_attachment(tmp_path: Path):
    from intelligence.attachments import materialize_attachments, format_attachments_block

    src = tmp_path / "note.txt"
    src.write_text("hello attach\nline2", encoding="utf-8")
    bus = tmp_path / "bus"
    items = materialize_attachments("t1", [src], bus_root=bus)
    assert items and items[0]["kind"] == "text"
    assert "hello attach" in (items[0].get("text") or "")
    stored = Path(items[0]["stored_as"])
    assert stored.is_file()
    block = format_attachments_block(items)
    assert "ATTACHMENTS" in block
    assert "hello attach" in block


def test_enrich_task_injects_message(tmp_path: Path):
    from intelligence.attachments import enrich_task_with_attachments

    src = tmp_path / "a.py"
    src.write_text("x = 1\n", encoding="utf-8")
    raw = {
        "id": "ui-1",
        "message": "fix this",
        "metadata": {"attachment_paths": [str(src)]},
    }
    out = enrich_task_with_attachments(raw, bus_root=tmp_path / "bus")
    assert "ATTACHMENTS" in out["message"]
    assert "USER REQUEST" in out["message"]
    assert out["metadata"]["attachments"]


def test_image_kind(tmp_path: Path):
    from intelligence.attachments import materialize_attachments

    img = tmp_path / "shot.png"
    # minimal PNG header bytes
    img.write_bytes(
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
        b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0c"
        b"IDATx\x9cc\xf8\x0f\x00\x01\x01\x01\x00\x18\xdd\x8d\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    items = materialize_attachments("img1", [img], bus_root=tmp_path / "bus")
    assert items[0]["kind"] == "image"
    assert items[0].get("caption")


def test_verify_policy_injects_on_high_complexity():
    from core.verify_policy import apply_verify_policy

    raw = {"message": "refactor", "verify": [], "metadata": {"complexity": 4}}
    out = apply_verify_policy(raw)
    assert out.get("verify")
    assert out["metadata"].get("verify_policy") == "injected_ladder"
    assert out["metadata"].get("verify_ladder") == 3
    assert out["metadata"].get("verify_max_level") == 3


def test_verify_ladder_autopilot_stricter():
    from core.verify_policy import required_ladder_level

    raw = {"message": "x", "metadata": {"complexity": 2, "source": "autopilot"}}
    assert required_ladder_level(raw) >= 2


def test_verify_policy_keeps_existing():
    from core.verify_policy import apply_verify_policy

    raw = {"verify": ["pytest -q"], "metadata": {"complexity": 5}}
    out = apply_verify_policy(raw)
    assert out["verify"] == ["pytest -q"]


def test_feature_flags_set_save(tmp_path: Path, monkeypatch):
    from core import feature_flags as ff

    path = tmp_path / "feature_flags.yaml"
    path.write_text("features:\n  conversation: true\n  attachments: true\n", encoding="utf-8")
    monkeypatch.setenv("AGENTBUS_FEATURE_FLAGS", str(path))
    ff.reload_flags()
    ff.set_flag("conversation", False)
    saved = ff.save_flags(path)
    assert saved == path
    text = path.read_text(encoding="utf-8")
    assert "conversation: false" in text
    ff.reload_flags()
    assert ff.is_enabled("conversation") is False
    ff.set_flag("conversation", True)
    ff.save_flags(path)


def test_autopilot_emit_has_nonempty_verify():
    from skills.autopilot import GeneratedTask

    t = GeneratedTask(
        message="add docstring to foo",
        files=["a.py"],
        priority=3,
        category="docs",
        confidence=0.8,
        source_rule="missing_docstrings",
    )
    payload = t.to_bus_payload(project="demo")
    assert payload["verify"], "autopilot must not emit empty verify"
    assert payload["metadata"].get("source") == "autopilot"
    assert int(payload["metadata"].get("verify_ladder") or 0) >= 2


def test_cache_put_skips_without_ladder(tmp_path, monkeypatch):
    """_cache_put must no-op when verify_ladder < 1 (non-skill)."""
    import sys
    from pathlib import Path

    # minimal Task-like
    class T:
        id = "x"
        files = []
        verify = []
        metadata = {"verify_ladder": 0, "complexity": 3}
        complexity = 3

    # Use Runtime method in isolation
    sys.path.insert(0, str(Path("src").resolve()))
    from core.runtime import Runtime

    class FakeLog:
        def __init__(self):
            self.lines = []
        def write(self, s):
            self.lines.append(s)

    rt = Runtime.__new__(Runtime)
    rt.log = FakeLog()
    # should return early without ImportError on GLOBAL_CACHE if ladder blocks first
    rt._cache_put(T(), tmp_path, method="llm", worker="w", snapshot=False)
    assert any("cache skip" in x for x in rt.log.lines)
