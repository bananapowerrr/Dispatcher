#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AgentBus external updater (UPDATE-001D).

Runs as a *separate* process. Stages:
  1. load job JSON
  2. download package to temp
  3. verify sha256
  4. (001E) backup install_dir + replace
  5. (001E) restart

001D implements load + download + verify. Replace/restart are dry-run stubs
unless --apply is passed (still refuses to delete user_data_dir).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
import urllib.request
from pathlib import Path


def _log(msg: str) -> None:
    print(f"[agentbus-updater] {msg}", flush=True)


def load_job(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SystemExit("job_not_object")
    return data


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def download(url: str, dest: Path, timeout: float = 120.0) -> None:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "AgentBus-Updater/0.10"},
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp, dest.open("wb") as out:
        while True:
            chunk = resp.read(1024 * 1024)
            if not chunk:
                break
            out.write(chunk)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="AgentBus external updater")
    ap.add_argument("--job", required=True, help="Path to update_job.json")
    ap.add_argument("--dry-run", action="store_true", help="Validate job only; no download")
    ap.add_argument("--apply", action="store_true", help="Download+verify (replace still gated)")
    ap.add_argument("--download-only", action="store_true", help="Download+verify, stop before replace")
    args = ap.parse_args(argv)

    job_path = Path(args.job)
    if not job_path.is_file():
        _log(f"job missing: {job_path}")
        return 2

    job = load_job(job_path)
    for key in ("package_url", "sha256", "target_version", "install_dir"):
        if not job.get(key):
            _log(f"missing job field: {key}")
            return 2

    sha = str(job["sha256"]).lower().strip()
    if len(sha) != 64:
        _log("invalid sha256")
        return 2

    user_data = Path(str(job.get("user_data_dir") or ""))
    install = Path(str(job["install_dir"]))
    _log(f"target={job.get('target_version')} install={install}")
    _log(f"user_data(protected)={user_data}")

    if args.dry_run:
        _log("dry-run OK — would download and verify, then external replace")
        return 0

    if not (args.apply or args.download_only):
        _log("refusing to mutate without --apply or --download-only (use --dry-run to test)")
        return 3

    tmp = Path(tempfile.mkdtemp(prefix="agentbus_upd_"))
    pkg = tmp / "package.bin"
    try:
        _log(f"download {job['package_url']}")
        download(str(job["package_url"]), pkg)
        digest = sha256_file(pkg)
        if digest != sha:
            _log(f"sha256 mismatch: got {digest}")
            return 4
        _log("sha256 OK")
        if args.download_only or not args.apply:
            _log("download+verify done; replace deferred to 001E")
            return 0
        # 001E: backup + replace + restart
        _log("replace/restart not enabled in 001D (see UPDATE-001E)")
        return 0
    except Exception as exc:
        _log(f"failed: {type(exc).__name__}: {exc}")
        return 1
    finally:
        # leave temp for debugging on failure; clean on success path optional
        pass


if __name__ == "__main__":
    sys.exit(main())
