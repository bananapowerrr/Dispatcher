"""FilesService.search case / glob options."""
from __future__ import annotations

from pathlib import Path

from app.files_service import FilesService


def test_search_case_and_glob(tmp_path: Path):
    (tmp_path / "a.py").write_text("Hello World\nhello world\n", encoding="utf-8")
    (tmp_path / "b.txt").write_text("Hello World\n", encoding="utf-8")
    fs = FilesService(str(tmp_path))

    all_hits = fs.search("Hello")
    assert len(all_hits) >= 2

    case = fs.search("Hello", case_sensitive=True)
    assert case
    assert all("Hello" in h["text"] for h in case)

    only_py = fs.search("Hello", glob="*.py")
    assert only_py
    assert all(h["path"].endswith(".py") for h in only_py)
