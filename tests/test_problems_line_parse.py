"""Problems collect extracts file:line from error messages."""
from __future__ import annotations

import json
from pathlib import Path

from ui.problems_panel import collect_problems


def test_collect_parses_file_line(tmp_path: Path):
    ab = tmp_path / ".agentbus" / "errors"
    ab.mkdir(parents=True)
    (ab / "t1.json").write_text(
        json.dumps({
            "id": "t1",
            "status": "ERROR",
            "error": "SyntaxError in src/foo.py:42: invalid syntax",
            "files": ["src/foo.py"],
        }),
        encoding="utf-8",
    )
    rows = collect_problems(tmp_path)
    assert rows
    assert rows[0]["file"] == "src/foo.py"
    assert int(rows[0].get("line") or 0) == 42
