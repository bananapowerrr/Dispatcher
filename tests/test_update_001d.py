# -*- coding: utf-8 -*-
import json
from pathlib import Path


def test_validate_job():
    from app.updater_protocol import build_update_job, validate_update_job

    check = {
        "current": "0.10.0",
        "latest": "0.10.1",
        "package_url": "https://example.com/p.zip",
        "sha256": "a" * 64,
        "update_available": True,
    }
    job = build_update_job(check=check, install_dir="/tmp/agentbus_install")
    ok, err = validate_update_job(job)
    assert ok, err
    bad = dict(job)
    bad["sha256"] = "short"
    ok2, err2 = validate_update_job(bad)
    assert not ok2


def test_write_and_dry_run_updater(tmp_path: Path):
    from app.updater_protocol import build_update_job, write_update_job, launch_updater

    check = {
        "current": "0.1.0",
        "latest": "0.2.0",
        "package_url": "https://example.com/p.zip",
        "sha256": "b" * 64,
    }
    job = build_update_job(check=check, install_dir=tmp_path / "inst")
    job_path = write_update_job(job, tmp_path / "job.json")
    script = Path("/home/workdir/artifacts/scripts/agentbus_updater.py")
    assert script.is_file()
    result = launch_updater(job_path, updater=script, dry_run=True, wait=True)
    assert result.get("ok") is True
    assert result.get("returncode") == 0


def test_prepare_requires_update():
    from app.updater_protocol import prepare_and_launch_from_check

    r = prepare_and_launch_from_check({"update_available": False}, dry_run=True)
    assert r["ok"] is False
