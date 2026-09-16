# -*- coding: utf-8 -*-
"""Offline e2e for file-bus claim path (no workers, no network)."""
from __future__ import annotations
import json
import tempfile
import uuid
from pathlib import Path

import pytest


def test_security_rejects_bad_verify_command():
    from security import validate_task, SecurityError
    with pytest.raises(SecurityError):
        validate_task({
            "id": "t1",
            "message": "x",
            "files": [],
            "verify": ["rm -rf /"],
        })


def test_filebus_write_and_claim_structure(tmp_path: Path):
    try:
        from bus import FileBus
    except ImportError:
        pytest.skip("bus not importable offline")

    channels = ["default"]
    bus = FileBus(tmp_path, channels)
    bus.ensure()
    tid = str(uuid.uuid4())
    payload = {
        "id": tid,
        "message": "noop",
        "files": [],
        "verify": ["pytest -q"],
        "channel": "default",
    }
    name = f"{tid}.json"
    bus.write("default", "incoming", name, json.dumps(payload, ensure_ascii=False))
    incoming = bus.paths("default")["incoming"]
    assert (incoming / name).is_file()
    assert bus.move("default", "incoming", "processing", name)
    assert not (incoming / name).exists()
    assert (bus.paths("default")["processing"] / name).is_file()


def test_project_validate_commands_hook():
    from project import ProjectContext
    ctx = ProjectContext(tempfile.gettempdir())
    ctx.validate_commands(verify=["pytest -q"], run=[])
    with pytest.raises(ValueError):
        ctx.validate_commands(verify=["rm -rf /"], run=[])
