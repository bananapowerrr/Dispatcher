"""Recent files JSON roundtrip (no GUI)."""
from __future__ import annotations

import json
from pathlib import Path


def test_recent_files_json_roundtrip(tmp_path: Path):
    path = tmp_path / ".agentbus" / "recent_files.json"
    path.parent.mkdir(parents=True)
    data = {"files": ["src/a.py", "src/b.py"]}
    path.write_text(json.dumps(data), encoding="utf-8")
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["files"][0] == "src/a.py"
    assert len(loaded["files"]) == 2
