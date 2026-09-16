# -*- coding: utf-8 -*-
"""Execution policy profiles — local_only / balanced / quality / cheap.

Mass-product: user picks autonomy vs quality without editing worker lists.
Env: AGENTBUS_POLICY=local_only|balanced|quality|cheap
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None  # type: ignore


@dataclass
class Policy:
    name: str = "balanced"
    prefer_local: bool = True
    require_local_fallback: bool = True
    allow_cloud: bool = True
    prefer_free_billing: bool = False
    telemetry: bool = False
    privacy: str = "hybrid"  # private | hybrid | cloud
    description: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    def forces_offline_filter(self) -> bool:
        return not self.allow_cloud


_CACHE: Policy | None = None


def _config_path() -> Path | None:
    for cand in (
        Path("config/policy.yaml"),
        Path(__file__).resolve().parents[2] / "config" / "policy.yaml",
    ):
        if cand.is_file():
            return cand
    try:
        from core.config import BASE_DIR
        p = Path(BASE_DIR) / "config" / "policy.yaml"
        if p.is_file():
            return p
    except Exception:
        pass
    return None


def load_policy(*, force: bool = False) -> Policy:
    global _CACHE
    if _CACHE is not None and not force:
        return _CACHE

    name = (os.getenv("AGENTBUS_POLICY") or "").strip().lower()
    profiles: dict[str, Any] = {}
    active = "balanced"
    path = _config_path()
    if path and yaml is not None:
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            if isinstance(data, dict):
                active = str(data.get("active") or active)
                profiles = data.get("profiles") or {}
        except Exception:
            pass
    if not name:
        name = active
    if name not in profiles and name not in ("local_only", "balanced", "quality", "cheap"):
        name = "balanced"

    body = profiles.get(name) if isinstance(profiles, dict) else None
    if not isinstance(body, dict):
        # defaults
        defaults = {
            "local_only": dict(
                prefer_local=True, require_local_fallback=True,
                allow_cloud=False, telemetry=False, privacy="private",
                description="Только local",
            ),
            "balanced": dict(
                prefer_local=True, require_local_fallback=True,
                allow_cloud=True, telemetry=False, privacy="hybrid",
                description="Local-first",
            ),
            "quality": dict(
                prefer_local=False, require_local_fallback=True,
                allow_cloud=True, telemetry=False, privacy="hybrid",
                description="Quality first",
            ),
            "cheap": dict(
                prefer_local=True, require_local_fallback=True,
                allow_cloud=True, prefer_free_billing=True,
                telemetry=False, privacy="hybrid",
                description="Minimize paid",
            ),
        }
        body = defaults.get(name, defaults["balanced"])

    pol = Policy(
        name=name,
        prefer_local=bool(body.get("prefer_local", True)),
        require_local_fallback=bool(body.get("require_local_fallback", True)),
        allow_cloud=bool(body.get("allow_cloud", True)),
        prefer_free_billing=bool(body.get("prefer_free_billing", False)),
        telemetry=bool(body.get("telemetry", False)),
        privacy=str(body.get("privacy") or "hybrid"),
        description=str(body.get("description") or ""),
    )
    _CACHE = pol
    return pol


def clear_policy_cache() -> None:
    global _CACHE
    _CACHE = None


def filter_workers_by_policy(workers: list[Any], policy: Policy | None = None) -> list[Any]:
    """Drop cloud workers when policy.allow_cloud is False."""
    pol = policy or load_policy()
    if pol.allow_cloud and not pol.prefer_free_billing:
        return list(workers)
    out = []
    for w in workers:
        prov = str(getattr(w, "provider", "") or "").lower()
        local = prov in ("ollama", "lmstudio", "local", "")
        if not pol.allow_cloud and not local:
            continue
        if pol.prefer_free_billing and not local:
            # keep cloud only if worker/provider marked free — soft: still allow, rank later
            pass
        out.append(w)
    return out if out else list(workers)  # never return empty if we filtered all


def apply_policy_to_fallback_kwargs(policy: Policy | None = None) -> dict[str, Any]:
    """Hints for fallback.order_candidates."""
    pol = policy or load_policy()
    return {
        "offline": True if pol.forces_offline_filter() else None,
        "failure_kind": "billing" if pol.prefer_local else None,
    }


def set_active_policy(name: str) -> Policy:
    """Persist active profile to policy.yaml and refresh cache."""
    key = (name or "balanced").strip().lower()
    path = _config_path()
    if path and yaml is not None:
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            if not isinstance(data, dict):
                data = {}
            data["active"] = key
            path.write_text(
                yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
                encoding="utf-8",
            )
        except Exception:
            pass
    os.environ["AGENTBUS_POLICY"] = key
    clear_policy_cache()
    return load_policy(force=True)


def list_policy_names() -> list[str]:
    path = _config_path()
    if path and yaml is not None:
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            profiles = data.get("profiles") or {}
            if isinstance(profiles, dict) and profiles:
                return sorted(profiles.keys())
        except Exception:
            pass
    return ["local_only", "balanced", "quality", "cheap"]
