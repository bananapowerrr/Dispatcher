# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path

from refactorer import (
    add_none_return_annotations,
    remove_unused_imports,
    try_refactor_from_message,
)


def test_remove_unused(tmp_path: Path) -> None:
    f = tmp_path / "u.py"
    f.write_text("import os\nimport sys\n\nx = 1\n", encoding="utf-8")
    r = remove_unused_imports(f, root=tmp_path)
    assert r.ok
    assert r.changed
    text = f.read_text(encoding="utf-8")
    assert "import os" not in text
    assert "import sys" not in text
    assert "x = 1" in text


def test_add_none(tmp_path: Path) -> None:
    f = tmp_path / "n.py"
    f.write_text("def bar():\n    x = 1\n\ndef foo():\n    return 2\n", encoding="utf-8")
    r = add_none_return_annotations(f, root=tmp_path)
    assert r.ok
    text = f.read_text(encoding="utf-8")
    assert "def bar() -> None:" in text
    assert "def foo()" in text and "-> None" not in text.split("def foo()")[1].split("\n")[0]


def test_try_from_message(tmp_path: Path) -> None:
    f = tmp_path / "m.py"
    f.write_text("import json\n\ndef z():\n    pass\n", encoding="utf-8")
    r = try_refactor_from_message("удали неиспользуемые импорты", [str(f)], root=tmp_path)
    assert r is not None and r.ok and r.changed


if __name__ == "__main__":
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        test_remove_unused(Path(d))
        test_add_none(Path(d))
        test_try_from_message(Path(d))
    print("OK")
