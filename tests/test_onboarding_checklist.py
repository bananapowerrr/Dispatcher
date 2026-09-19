"""Onboarding checklist offline."""
from __future__ import annotations

from app.onboarding_checklist import check_items, format_checklist, checklist_score


def test_check_items_shape():
    rows = check_items(None)
    assert len(rows) >= 4
    assert all("id" in r and "ok" in r and "label" in r for r in rows)


def test_format_has_score():
    text = format_checklist(project_root=None)
    assert "NVCode" in text or "готовность" in text
    assert "✓" in text or "○" in text


def test_score_tuple():
    a, b = checklist_score(None)
    assert 0 <= a <= b
    assert b >= 4
