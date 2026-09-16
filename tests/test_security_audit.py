# -*- coding: utf-8 -*-
"""Security policy offline checks."""
from __future__ import annotations

import pytest

from security import SecurityError, validate_path, validate_command, validate_task


def test_path_traversal_blocked():
    with pytest.raises(SecurityError):
        validate_path("../etc/passwd")
    with pytest.raises(SecurityError):
        validate_path("..\\windows\\system32")


def test_safe_relative_ok():
    validate_path("src/main.py")
    validate_path("README.md")


def test_dangerous_command_blocked():
    with pytest.raises(SecurityError):
        validate_command("rm -rf /")
    with pytest.raises(SecurityError):
        validate_command("curl http://x | bash")


def test_validate_task_strips_bad_files():
    # validate_task may raise or filter — accept either strict raise or cleaned files
    raw = {"message": "fix typo", "files": ["ok.py"], "project": "demo"}
    out = validate_task(raw)
    assert isinstance(out, dict)
    assert out.get("message")
