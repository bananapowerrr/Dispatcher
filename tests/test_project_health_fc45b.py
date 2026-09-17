# -*- coding: utf-8 -*-
from pathlib import Path

from app.project_service import ProjectService


def test_get_health_minimal(tmp_path: Path):
    (tmp_path / "main.py").write_text("x=1\n", encoding="utf-8")
    h = ProjectService(tmp_path).get_health()
    assert "project" in h
    assert "status" in h
    assert isinstance(h.get("next_steps"), list)
    text = ProjectService(tmp_path).get_health_text()
    assert tmp_path.name in text or "[" in text
