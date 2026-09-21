# -*- coding: utf-8 -*-
from pathlib import Path

def test_day20_constraints_doc():
    paths = [
        Path(__file__).resolve().parents[1] / "docs" / "DAY20_NIGHT_MODE_CONSTRAINTS.md",
        Path("/home/workdir/artifacts/docs/DAY20_NIGHT_MODE_CONSTRAINTS.md"),
    ]
    p = next(x for x in paths if x.is_file())
    text = p.read_text(encoding="utf-8")
    assert "MAX_PARALLEL_PROJECTS" in text
    assert "false DONE" in text.lower() or "false DONE" in text
    assert "Not implemented offline" in text or "docs only" in text.lower()


def test_index_lists_days():
    paths = [
        Path(__file__).resolve().parents[1] / "docs" / "INDEX_OFFLINE_DAYS_13_20.md",
        Path("/home/workdir/artifacts/docs/INDEX_OFFLINE_DAYS_13_20.md"),
    ]
    p = next(x for x in paths if x.is_file())
    text = p.read_text(encoding="utf-8")
    for d in ("13.1", "14", "15", "16", "17", "18", "19", "20"):
        assert d in text


def test_optional_string_keys_if_present():
    for lang in ("ru", "en"):
        p = Path(f"/home/workdir/artifacts/strings_{lang}.yaml")
        if not p.is_file():
            continue
        text = p.read_text(encoding="utf-8")
        assert "settings_read_only:" in text
