# -*- coding: utf-8 -*-
"""Offline tests for unified intake pipeline."""
from __future__ import annotations

import pytest

from core.intake_pipeline import IntakeError, accept_task_raw, try_accept_task_raw


def test_accept_ok():
    task = accept_task_raw(
        {"message": "format code", "files": ["src/a.py"], "project": "."},
        source="desktop",
    )
    assert task.message
    assert task.metadata.get("intake_source") == "desktop"


def test_reject_empty():
    with pytest.raises(IntakeError):
        accept_task_raw(None, source="cli")


def test_reject_path_traversal():
    with pytest.raises(IntakeError):
        accept_task_raw(
            {
                "message": "read secrets",
                "files": ["../../etc/passwd"],
                "project": ".",
            },
            source="filebus",
        )


def test_try_accept_soft():
    task, err = try_accept_task_raw({"message": "ok"}, source="recipe")
    assert task is not None and err is None
    task2, err2 = try_accept_task_raw(None, source="recipe")
    assert task2 is None and err2
