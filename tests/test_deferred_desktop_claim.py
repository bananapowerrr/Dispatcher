# -*- coding: utf-8 -*-
"""PC-25: deferred/stuck desktop tasks must be claimable without phone_filebus."""
from __future__ import annotations

import json
from pathlib import Path


def test_active_channels_includes_desktop():
    from core.runtime_ops import RuntimeOps

    # CHANNELS may not list desktop; product path requires it
    src = Path(__file__).resolve().parents[1] / "src" / "core" / "runtime_ops.py"
    text = src.read_text(encoding="utf-8")
    assert 'list(CHANNELS) + ["desktop"]' in text
    assert "def _claim_desktop_incoming" in text


def test_deferred_desktop_recover_then_claim(tmp_path: Path):
    from core.bus import FileBus
    from core.runtime_ops import RuntimeOps

    bus = FileBus(tmp_path, channels=("gpt", "desktop"))
    bus.ensure()
    tid = "ui-deferred-1"
    payload = {
        "id": tid,
        "message": "resume me please",
        "channel": "desktop",
        "project": str(tmp_path),
        "status": "DEFERRED",
        "files": [],
        "metadata": {"primary_channel": "desktop"},
    }
    bus.write("desktop", "deferred", f"{tid}.json", json.dumps(payload, ensure_ascii=False))
    assert bus.move("desktop", "deferred", "incoming", f"{tid}.json")
    assert (tmp_path / "channels" / "desktop" / "incoming" / f"{tid}.json").is_file()

    class _Log:
        def write(self, msg: str) -> None:
            pass

    ops = RuntimeOps.__new__(RuntimeOps)
    ops.bus = bus
    ops.log = _Log()

    raw = ops._claim_desktop_incoming()
    assert raw is not None, "desktop/incoming must be claimed without phone_filebus"
    assert str(raw.get("id") or "") == tid or "resume" in str(raw.get("message") or "")
    assert (tmp_path / "channels" / "desktop" / "processing" / f"{tid}.json").is_file()
    assert not (tmp_path / "channels" / "desktop" / "incoming" / f"{tid}.json").is_file()


def test_only_channels_desktop_skips_gpt(tmp_path: Path):
    from core.bus import FileBus
    from core.runtime_ops import RuntimeOps

    bus = FileBus(tmp_path, channels=("gpt", "desktop"))
    bus.ensure()
    bus.write(
        "gpt",
        "incoming",
        "gpt-only.json",
        json.dumps({"id": "gpt-only", "message": "phone task", "channel": "gpt", "project": str(tmp_path)}),
    )

    class _Log:
        def write(self, msg: str) -> None:
            pass

    ops = RuntimeOps.__new__(RuntimeOps)
    ops.bus = bus
    ops.log = _Log()

    raw = ops._claim_file_task(only_channels=("desktop",))
    assert raw is None  # gpt must not be claimed via desktop-only filter
    assert (tmp_path / "channels" / "gpt" / "incoming" / "gpt-only.json").is_file()
