# -*- coding: utf-8 -*-
"""PC-27: early ERROR/DONE must write terminal JSON for UI pending_ids."""
from __future__ import annotations

import json
from pathlib import Path


def test_finalize_early_terminal_error(tmp_path: Path):
    from core.bus import FileBus
    from core.rp_lifecycle import RPLifecycleMixin
    from core.runtime_ops import RuntimeOps

    bus = FileBus(tmp_path, channels=("gpt", "desktop"))
    bus.ensure()
    tid = "ui-hook-1"
    raw = {
        "id": tid,
        "message": "x",
        "channel": "desktop",
        "project": str(tmp_path),
        "files": [],
    }
    bus.write("desktop", "processing", f"{tid}.json", json.dumps(raw))

    class _Log:
        def write(self, msg: str) -> None:
            pass

    class T(RPLifecycleMixin, RuntimeOps):
        pass

    obj = T.__new__(T)
    obj.bus = bus
    obj.log = _Log()
    obj._save = lambda task, state, result: RuntimeOps._save(obj, task, state, result)

    obj._finalize_early_terminal(
        raw,
        state="errors",
        result={"error": "pre_hook abort: test", "method": "pre_hook", "worker": "hooks"},
    )
    err = tmp_path / "channels" / "desktop" / "errors" / f"{tid}.json"
    assert err.is_file()
    data = json.loads(err.read_text(encoding="utf-8"))
    blob = str(data.get("result") or data)
    assert "pre_hook" in blob or "abort" in blob


def test_lifecycle_has_early_terminal_hooks():
    src = Path(__file__).resolve().parents[1] / "src" / "core" / "rp_lifecycle.py"
    text = src.read_text(encoding="utf-8")
    assert "def _finalize_early_terminal" in text
    assert '_finalize_early_terminal' in text
    assert "pre_hook abort" in text or "method\": \"pre_hook\"" in text or "method': 'pre_hook'" in text or 'method": "pre_hook"' in text
    assert "method\": \"decompose\"" in text or 'method": "decompose"' in text
