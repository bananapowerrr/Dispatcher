# -*- coding: utf-8 -*-
"""PC-26: DEDUPED must write terminal done JSON so UI pending_ids clears."""
from __future__ import annotations

import json
from pathlib import Path


def test_finalize_deduped_writes_done(tmp_path: Path):
    from core.bus import FileBus
    from core.runtime import Runtime
    from core.runtime_ops import RuntimeOps
    from ui.result_text import extract_result_text

    bus = FileBus(tmp_path, channels=("gpt", "desktop"))
    bus.ensure()
    tid = "ui-dup-1"
    raw = {
        "id": tid,
        "message": "same task",
        "channel": "desktop",
        "project": str(tmp_path),
        "files": [],
    }
    bus.write("desktop", "processing", f"{tid}.json", json.dumps(raw))

    class _Log:
        def write(self, msg: str) -> None:
            pass

    rt = Runtime.__new__(Runtime)
    rt.bus = bus
    rt.log = _Log()
    rt._save = lambda task, state, result: RuntimeOps._save(rt, task, state, result)

    Runtime._finalize_deduped(rt, raw, reason="completed")
    done = tmp_path / "channels" / "desktop" / "done" / f"{tid}.json"
    assert done.is_file()
    data = json.loads(done.read_text(encoding="utf-8"))
    text = extract_result_text(data)
    assert "дубликат" in text or "dedupe" in text.lower()
