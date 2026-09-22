# -*- coding: utf-8 -*-
"""UPDATE-001D: external updater job protocol.

AgentBus never replaces its own running binaries.
It writes a job file and launches `agentbus_updater` as a separate process.

Job schema (JSON):
  version: 1
  action: install
  current_version, target_version
  package_url, sha256
  install_dir, backup_dir, user_data_dir
  restart_cmd (optional list)
  app_pid (optional — updater may wait/signal)
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

JOB_VERSION = 1
REQUIRED_JOB_KEYS = (
    "version",
    "action",
    "target_version",
    "package_url",
    "sha256",
    "install_dir",
)


def validate_update_job(job: dict[str, Any] | None) -> tuple[bool, str]:
    if not isinstance(job, dict):
        return False, "job_not_object"
    for k in REQUIRED_JOB_KEYS:
        if k not in job or job[k] in (None, ""):
            return False, f"missing:{k}"
    if int(job.get("version") or 0) != JOB_VERSION:
        return False, "unsupported_job_version"
    if str(job.get("action") or "") != "install":
        return False, "unsupported_action"
    sha = str(job.get("sha256") or "").strip().lower()
    if len(sha) != 64 or any(c not in "0123456789abcdef" for c in sha):
        return False, "sha256_invalid"
    url = str(job.get("package_url") or "")
    if not url.startswith(("https://", "http://")):
        return False, "package_url_invalid"
    return True, ""


def build_update_job(
    *,
    check: dict[str, Any] | None = None,
    install_dir: str | Path | None = None,
    backup_dir: str | Path | None = None,
    user_data_dir: str | Path | None = None,
    restart_cmd: list[str] | None = None,
    app_pid: int | None = None,
    current_version: str = "",
) -> dict[str, Any]:
    """Build job from UpdateChecker result + paths."""
    c = dict(check or {})
    install = Path(install_dir or os.getenv("AGENTBUS_INSTALL_DIR") or Path.cwd())
    backup = Path(
        backup_dir
        or os.getenv("AGENTBUS_BACKUP_DIR")
        or (install / ".agentbus_backup")
    )
    user_data = Path(
        user_data_dir
        or os.getenv("AGENTBUS_USER_DATA")
        or Path.home() / "AppData" / "Roaming" / "AgentBus"
    )
    job: dict[str, Any] = {
        "version": JOB_VERSION,
        "action": "install",
        "current_version": current_version or str(c.get("current") or ""),
        "target_version": str(c.get("latest") or ""),
        "package_url": str(c.get("package_url") or ""),
        "sha256": str(c.get("sha256") or "").lower(),
        "install_dir": str(install.resolve()),
        "backup_dir": str(backup.resolve()),
        "user_data_dir": str(user_data),
        "notes": str(c.get("notes") or ""),
        "channel": str(c.get("channel") or "stable"),
    }
    if restart_cmd:
        job["restart_cmd"] = list(restart_cmd)
    if app_pid:
        job["app_pid"] = int(app_pid)
    return job


def write_update_job(job: dict[str, Any], path: str | Path) -> Path:
    ok, err = validate_update_job(job)
    if not ok:
        raise ValueError(f"invalid_update_job:{err}")
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


def default_job_path() -> Path:
    base = os.getenv("AGENTBUS_USER_DATA")
    if base:
        return Path(base) / "update_job.json"
    return Path.home() / "AppData" / "Roaming" / "AgentBus" / "update_job.json"


def find_updater_script() -> Path | None:
    """Locate scripts/agentbus_updater.py relative to install / repo."""
    env = os.getenv("AGENTBUS_UPDATER")
    if env and Path(env).is_file():
        return Path(env)
    here = Path(__file__).resolve()
    candidates = [
        here.parents[2] / "scripts" / "agentbus_updater.py",
        here.parents[1] / "scripts" / "agentbus_updater.py",
        Path.cwd() / "scripts" / "agentbus_updater.py",
    ]
    for c in candidates:
        if c.is_file():
            return c
    return None


def launch_updater(
    job_path: str | Path,
    *,
    updater: str | Path | None = None,
    dry_run: bool = False,
    wait: bool = False,
) -> dict[str, Any]:
    """Spawn external updater process. Does not install from this process."""
    job_p = Path(job_path)
    if not job_p.is_file():
        return {"ok": False, "error": "job_file_missing", "pid": None}
    script = Path(updater) if updater else find_updater_script()
    if script is None or not script.is_file():
        return {"ok": False, "error": "updater_not_found", "pid": None}

    cmd = [sys.executable, str(script), "--job", str(job_p)]
    if dry_run:
        cmd.append("--dry-run")
    try:
        if wait:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
            return {
                "ok": proc.returncode == 0,
                "returncode": proc.returncode,
                "stdout": (proc.stdout or "")[-2000:],
                "stderr": (proc.stderr or "")[-1000:],
                "pid": None,
                "dry_run": dry_run,
            }
        proc = subprocess.Popen(cmd)  # noqa: S603 — controlled paths
        return {"ok": True, "pid": proc.pid, "dry_run": dry_run}
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}", "pid": None}


def prepare_and_launch_from_check(
    check: dict[str, Any],
    *,
    install_dir: str | Path | None = None,
    dry_run: bool = True,
    wait: bool = False,
) -> dict[str, Any]:
    """Convenience: validate check → write job → launch updater (default dry-run)."""
    if not check.get("update_available") or not check.get("package_url"):
        return {"ok": False, "error": "no_update_to_apply"}
    job = build_update_job(check=check, install_dir=install_dir)
    ok, err = validate_update_job(job)
    if not ok:
        return {"ok": False, "error": err}
    path = write_update_job(job, default_job_path())
    launched = launch_updater(path, dry_run=dry_run, wait=wait)
    launched["job_path"] = str(path)
    return launched
