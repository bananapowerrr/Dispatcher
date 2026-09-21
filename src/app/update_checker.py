# -*- coding: utf-8 -*-
"""UpdateChecker (UPDATE-001B skeleton).

Compares local version to remote release manifest.
Does NOT download or replace the running process.
"""
from __future__ import annotations

from typing import Any

from app.release_manifest import parse_manifest
from app.version import get_version, is_newer


DEFAULT_MANIFEST_URL = (
    "https://github.com/bananapowerrr/Dispatcher/releases/latest/download/release.json"
)


def compare_to_manifest(manifest: dict[str, Any] | None) -> dict[str, Any]:
    """Pure compare. No network."""
    current = get_version()
    out: dict[str, Any] = {
        "current": current,
        "latest": None,
        "update_available": False,
        "manifest_ok": False,
        "error": "",
        "notes": "",
        "package_url": "",
        "sha256": "",
    }
    if not manifest:
        out["error"] = "no_manifest"
        return out
    parsed, err = parse_manifest(manifest)
    if not parsed:
        out["error"] = err or "invalid_manifest"
        return out
    out["manifest_ok"] = True
    latest = str(parsed.get("version") or "")
    out["latest"] = latest
    out["notes"] = str(parsed.get("notes") or "")
    pkg = parsed.get("package") if isinstance(parsed.get("package"), dict) else {}
    out["package_url"] = str(pkg.get("url") or "")
    out["sha256"] = str(pkg.get("sha256") or "")
    out["update_available"] = is_newer(latest, current)
    return out


def check_update_from_text(manifest_json: str) -> dict[str, Any]:
    """Parse JSON text and compare (offline / test path)."""
    data, err = parse_manifest(manifest_json)
    if not data:
        return {
            "current": get_version(),
            "latest": None,
            "update_available": False,
            "manifest_ok": False,
            "error": err,
        }
    return compare_to_manifest(data)
