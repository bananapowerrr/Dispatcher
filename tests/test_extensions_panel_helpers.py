"""Extensions panel paths without GUI."""
from __future__ import annotations

from pathlib import Path


def test_plugins_dir_and_extensions_yaml():
    root = Path(__file__).resolve().parents[1]
    yaml = root / "config" / "extensions.yaml"
    assert yaml.is_file()
