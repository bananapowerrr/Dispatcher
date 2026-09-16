# -*- coding: utf-8 -*-
"""Soft plugin registry: feature flag → optional module import.

Core (bus, runtime, router, executor) is never registered here — only
optional intelligence/skills/safety layers that may be disabled.

Usage::

    from core.plugin_registry import load, status, soft_call

    conv = load("conversation")  # None if off or ImportError
    soft_call("codebase_rag", "get_rag", project_root)
"""
from __future__ import annotations

import importlib
import logging
from dataclasses import dataclass
from typing import Any, Callable

from core.feature_flags import is_enabled

logger = logging.getLogger("agentbus.plugins")

# feature name → dotted module path (under src/)
PLUGIN_MODULES: dict[str, str] = {
    "conversation": "intelligence.conversation",
    "session_memory": "intelligence.session_memory",
    "codebase_rag": "intelligence.codebase_rag",
    "semantic_memory": "intelligence.semantic_memory",
    "sub_agents": "intelligence.sub_agent",
    "autopilot": "skills.autopilot",
    "night_scheduler": "intelligence.night_scheduler",
    "skill_learner": "skills.skill_learner",
    "diff_preview": "safety.diff_engine",
    "solution_cache": "intelligence.solution_cache",
    "skills": "skills.skills",
    "meta_classifier": "skills.meta_classifier",
    "explainability": "utils.explainability",
    "hooks": "utils.hooks",
    "file_watcher": "utils.file_watcher",
    "cost_tracker": "utils.cost_tracker",
    "task_decomposer": "skills.task_decomposer",
    "project_index": "intelligence.project_index",
    "lesson_learner": "intelligence.lesson_learner",
    "attachments": "intelligence.attachments",
    "verify_policy": "core.verify_policy",
}

_CACHE: dict[str, Any | None] = {}
_ERRORS: dict[str, str] = {}


@dataclass
class PluginInfo:
    name: str
    module: str
    enabled: bool
    loaded: bool
    error: str = ""


def clear_cache() -> None:
    """Drop import cache (after flag change / hot-reload)."""
    _CACHE.clear()
    _ERRORS.clear()


def load(name: str, *, force: bool = False) -> Any | None:
    """Import plugin module if feature enabled. Never raises."""
    key = (name or "").strip().lower().replace("-", "_")
    if not key:
        return None
    if not force and key in _CACHE:
        return _CACHE[key]
    mod_path = PLUGIN_MODULES.get(key)
    if not mod_path:
        _CACHE[key] = None
        _ERRORS[key] = "unknown plugin"
        return None
    if not is_enabled(key, default=True):
        _CACHE[key] = None
        _ERRORS[key] = "disabled"
        logger.debug("plugin %s disabled", key)
        return None
    try:
        mod = importlib.import_module(mod_path)
        _CACHE[key] = mod
        _ERRORS.pop(key, None)
        return mod
    except Exception as exc:
        _CACHE[key] = None
        _ERRORS[key] = f"{type(exc).__name__}: {exc}"
        logger.warning("plugin %s import failed: %s", key, exc)
        return None


def soft_call(name: str, attr: str, *args: Any, default: Any = None, **kwargs: Any) -> Any:
    """Load plugin and call attribute; return *default* on any failure."""
    mod = load(name)
    if mod is None:
        return default
    fn = getattr(mod, attr, None)
    if fn is None or not callable(fn):
        return default
    try:
        return fn(*args, **kwargs)
    except Exception as exc:
        logger.warning("plugin %s.%s failed: %s", name, attr, exc)
        return default


def status() -> list[PluginInfo]:
    """Snapshot for diagnose / admin UI."""
    out: list[PluginInfo] = []
    for name, mod_path in sorted(PLUGIN_MODULES.items()):
        enabled = is_enabled(name, default=True)
        err = _ERRORS.get(name, "")
        loaded = name in _CACHE and _CACHE[name] is not None
        if enabled and name not in _CACHE:
            # probe without permanently failing unknown paths: optional probe
            load(name)
            loaded = _CACHE.get(name) is not None
            err = _ERRORS.get(name, "")
        out.append(
            PluginInfo(
                name=name,
                module=mod_path,
                enabled=enabled,
                loaded=loaded,
                error="" if loaded else err,
            )
        )
    return out


def status_dict() -> list[dict[str, Any]]:
    return [
        {
            "name": p.name,
            "module": p.module,
            "enabled": p.enabled,
            "loaded": p.loaded,
            "error": p.error,
        }
        for p in status()
    ]



# --- Mass-product extension API -------------------------------------------

def _extensions_yaml() -> dict:
    try:
        import yaml
        from pathlib import Path
        try:
            from core.config import BASE_DIR
            base = Path(BASE_DIR)
        except Exception:
            base = Path(__file__).resolve().parents[2]
        path = base / "config" / "extensions.yaml"
        if not path.is_file():
            return {}
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def register_plugin(name: str, module_path: str, *, enabled_default: bool = True) -> None:
    """Register a plugin at runtime (tests / dynamic load)."""
    key = (name or "").strip().lower().replace("-", "_")
    if not key or not module_path:
        return
    PLUGIN_MODULES[key] = module_path
    _CACHE.pop(key, None)
    _ERRORS.pop(key, None)


def load_extension_manifest() -> None:
    """Merge config/extensions.yaml into PLUGIN_MODULES."""
    data = _extensions_yaml()
    ext = data.get("extensions") or {}
    if not isinstance(ext, dict):
        return
    for name, cfg in ext.items():
        if not isinstance(cfg, dict):
            continue
        mod = str(cfg.get("module") or "").strip()
        if not mod:
            continue
        if cfg.get("enabled") is False:
            continue
        register_plugin(str(name), mod)


def discover_plugins() -> list[dict]:
    """Scan plugins/ for modules with EXTENSION dict."""
    import importlib
    import sys
    from pathlib import Path

    found: list[dict] = []
    try:
        from core.config import BASE_DIR
        roots = [Path(BASE_DIR)]
    except Exception:
        roots = [Path(__file__).resolve().parents[2]]

    data = _extensions_yaml()
    scan = list(data.get("scan_paths") or ["plugins", "src/plugins"])
    for root in roots:
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
        for rel in scan:
            d = root / rel
            if not d.is_dir():
                continue
            if str(d.parent) not in sys.path:
                sys.path.insert(0, str(d.parent))
            for py in d.glob("*.py"):
                if py.name.startswith("_"):
                    continue
                mod_name = f"{d.name}.{py.stem}"
                try:
                    mod = importlib.import_module(mod_name)
                except Exception:
                    continue
                meta = getattr(mod, "EXTENSION", None)
                if not isinstance(meta, dict):
                    continue
                name = str(meta.get("name") or py.stem)
                entry = {
                    "name": name,
                    "module": mod_name,
                    "enabled": bool(meta.get("enabled", False)),
                    "provides": list(meta.get("provides") or []),
                    "description": str(meta.get("description") or ""),
                }
                found.append(entry)
                if entry["enabled"]:
                    register_plugin(name, mod_name)
    return found


def capability_routing() -> dict:
    data = _extensions_yaml()
    cr = data.get("capability_routing") or {}
    return cr if isinstance(cr, dict) else {}


def list_providers_for_capability(cap: str) -> dict:
    """Hint which providers/harnesses fit a capability (offline-first defaults)."""
    rules = capability_routing().get(cap) or {}
    out = {"capability": cap, "rules": rules}
    try:
        from providers.registry import load_providers
        providers = load_providers()
        usable = []
        require_billing = rules.get("require_billing")
        for p in providers:
            if not p.is_usable():
                continue
            if require_billing and p.billing != require_billing:
                continue
            usable.append({"id": p.id, "billing": p.billing, "priority": p.priority})
        out["usable_providers"] = usable
    except Exception as exc:
        out["error"] = str(exc)
    return out


# Load manifest once on import (non-fatal)
try:
    load_extension_manifest()
except Exception:
    pass
