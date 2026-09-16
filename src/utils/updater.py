# -*- coding: utf-8 -*-
"""Optional GitHub Releases updater (disabled unless AGENTBUS_UPDATE_REPO set)."""
from __future__ import annotations

import json
import os
import urllib.request
from typing import Any


def _repo() -> str:
    return (os.getenv("AGENTBUS_UPDATE_REPO") or "").strip()


def check_for_updates(current_version: str = "0.1.0") -> dict[str, Any] | None:
    """Return release info if a newer tag exists, else None.

    Does nothing without AGENTBUS_UPDATE_REPO=owner/name.
    """
    repo = _repo()
    if not repo:
        return None
    url = f"https://api.github.com/repos/{repo}/releases/latest"
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "AgentBus"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None
    tag = str(data.get("tag_name") or "").lstrip("v")
    if not tag or tag <= current_version.lstrip("v"):
        return None
    assets = data.get("assets") or []
    download = ""
    if assets and isinstance(assets[0], dict):
        download = str(assets[0].get("browser_download_url") or "")
    return {
        "version": tag,
        "download_url": download,
        "changelog": str(data.get("body") or "")[:4000],
    }
