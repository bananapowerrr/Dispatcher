# -*- coding: utf-8 -*-
from pathlib import Path


def test_optional_string_keys_if_present():
    for lang in ("ru", "en"):
        p = Path(__file__).resolve().parent.parent / f"strings_{lang}.yaml"
        if not p.is_file():
            continue
        text = p.read_text(encoding="utf-8")
        assert "settings_read_only:" in text
