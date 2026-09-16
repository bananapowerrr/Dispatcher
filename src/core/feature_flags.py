# -*- coding: utf-8 -*-
"""Central feature flags with YAML + env overrides and graceful import helper.

Usage::

    from core.feature_flags import is_enabled, optional_import

    if is_enabled("conversation"):
        mod = optional_import("conversation")
        if mod is not None:
            ...

Env: ``AGENTBUS_FEATURE_CONVERSATION=0`` disables ``conversation``.
Missing config file → all known features default to True (safe for upgrades).
"""
from __future__ import annotations

import importlib
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger("agentbus.features")

# Canonical names (yaml keys / env suffix lower)
KNOWN_FEATURES: tuple[str, ...] = (
    "conversation",
    "session_memory",
    "codebase_rag",
    "semantic_memory",
    "sub_agents",
    "autopilot",
    "night_scheduler",
    "skill_learner",
    "diff_preview",
    "solution_cache",
    "skills",
    "meta_classifier",
    "explainability",
    "hooks",
    "file_watcher",
    "cost_tracker",
    "task_decomposer",
    "project_index",
    "lesson_learner",
    "attachments",
    "verify_policy",
    "phone_filebus",
    "remote_filebus",
)

_DEFAULTS: dict[str, bool] = {name: True for name in KNOWN_FEATURES}
# Optional remote modules off by default (desktop chat is primary)
_DEFAULTS["phone_filebus"] = False
_DEFAULTS["remote_filebus"] = False
_FLAGS: dict[str, bool] | None = None
_CONFIG_PATH: Path | None = None


def _config_candidates() -> list[Path]:
    here = Path(__file__).resolve().parent  # src/core
    root = here.parents[1]  # AgentBus root
    out: list[Path] = []
    env = os.getenv("AGENTBUS_FEATURE_FLAGS", "").strip()
    if env:
        out.append(Path(env))
    out.append(root / "config" / "feature_flags.yaml")
    out.append(root / "feature_flags.yaml")
    return out


def _coerce_bool(value: Any, default: bool = True) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    s = str(value).strip().lower()
    if s in {"1", "true", "yes", "on", "enable", "enabled"}:
        return True
    if s in {"0", "false", "no", "off", "disable", "disabled"}:
        return False
    return default


def _load_yaml_flags() -> dict[str, bool]:
    flags = dict(_DEFAULTS)
    path: Path | None = None
    for cand in _config_candidates():
        if cand.is_file():
            path = cand
            break
    global _CONFIG_PATH
    _CONFIG_PATH = path
    if path is None:
        return flags
    try:
        import yaml  # type: ignore
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        logger.warning("feature_flags: cannot read %s: %s", path, exc)
        return flags
    section = data.get("features") if isinstance(data, dict) else None
    if not isinstance(section, dict):
        section = data if isinstance(data, dict) else {}
    for key, val in section.items():
        name = str(key).strip().lower().replace("-", "_")
        flags[name] = _coerce_bool(val, flags.get(name, True))
    return flags


def _apply_env(flags: dict[str, bool]) -> dict[str, bool]:
    prefix = "AGENTBUS_FEATURE_"
    for key, value in os.environ.items():
        if not key.startswith(prefix):
            continue
        name = key[len(prefix) :].strip().lower().replace("-", "_")
        if not name:
            continue
        flags[name] = _coerce_bool(value, flags.get(name, True))
    return flags


def reload_flags() -> dict[str, bool]:
    """Force re-read YAML + env. Returns copy of active flags."""
    global _FLAGS
    _FLAGS = _apply_env(_load_yaml_flags())
    return dict(_FLAGS)


def get_flags() -> dict[str, bool]:
    """Current flags (lazy-loaded)."""
    global _FLAGS
    if _FLAGS is None:
        reload_flags()
    assert _FLAGS is not None
    return dict(_FLAGS)


def is_enabled(name: str, default: bool = True) -> bool:
    """Return whether feature *name* is enabled."""
    key = (name or "").strip().lower().replace("-", "_")
    if not key:
        return default
    flags = get_flags()
    return bool(flags.get(key, default))


def config_path() -> Path | None:
    """Path to YAML used (after first load), or None."""
    get_flags()
    return _CONFIG_PATH


def enabled_list() -> list[str]:
    return sorted(k for k, v in get_flags().items() if v)


def disabled_list() -> list[str]:
    return sorted(k for k, v in get_flags().items() if not v)


def optional_import(module_name: str, *, feature: str | None = None) -> Any | None:
    """Import module if feature enabled; return None on disable or ImportError.

    *feature* defaults to *module_name* (last dotted part normalized).
    """
    feat = feature or module_name.rsplit(".", 1)[-1]
    feat = feat.strip().lower().replace("-", "_")
    if not is_enabled(feat, default=True):
        logger.debug("feature_flags: skip import %s (feature %s off)", module_name, feat)
        return None
    try:
        return importlib.import_module(module_name)
    except Exception as exc:
        logger.warning(
            "feature_flags: import %s failed (feature %s): %s",
            module_name,
            feat,
            exc,
        )
        return None


def snapshot() -> dict[str, Any]:
    """For diagnose / metrics."""
    flags = get_flags()
    return {
        "config": str(_CONFIG_PATH) if _CONFIG_PATH else None,
        "enabled": sorted(k for k, v in flags.items() if v),
        "disabled": sorted(k for k, v in flags.items() if not v),
        "flags": dict(sorted(flags.items())),
    }



def set_flag(name: str, enabled: bool, *, save: bool = True) -> bool:
    """Set feature flag in memory; optionally persist to feature_flags.yaml.

    Args:
        name: feature key
        enabled: on/off
        save: if True (default), write YAML via save_flags()
    Returns:
        True if flag was applied
    """
    global _FLAGS
    key = (name or "").strip().lower().replace("-", "_")
    if not key:
        return False
    flags = get_flags()
    flags[key] = bool(enabled)
    _FLAGS = flags
    if save:
        try:
            save_flags()
        except Exception:
            # still applied in memory
            pass
    return True


def save_flags(path: Path | None = None) -> Path:
    """Write current flags to YAML. Returns path written."""
    flags = get_flags()
    ordered = {k: bool(flags.get(k, True)) for k in KNOWN_FEATURES}
    for k, v in sorted(flags.items()):
        if k not in ordered:
            ordered[k] = bool(v)
    target = path or config_path()
    if target is None:
        here = Path(__file__).resolve().parent
        target = here.parents[1] / "config" / "feature_flags.yaml"
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# AgentBus feature flags",
        "# Managed by admin_ui / feature_flags.save_flags",
        "# Env override: AGENTBUS_FEATURE_<NAME>=0|1",
        "",
        "features:",
    ]
    for k, v in ordered.items():
        lines.append(f"  {k}: {'true' if v else 'false'}")
    lines.append("")
    text = chr(10).join(lines)
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(target)
    reload_flags()
    return target


def list_features() -> list[dict]:
    """For admin UI: [{name, enabled, known}]."""
    flags = get_flags()
    known = set(KNOWN_FEATURES)
    names = sorted(set(flags) | known)
    return [
        {"name": n, "enabled": bool(flags.get(n, True)), "known": n in known}
        for n in names
    ]



def _presets_path() -> Path | None:
    here = Path(__file__).resolve().parent
    root = here.parents[1]
    for cand in (
        Path(os.getenv("AGENTBUS_FEATURE_PRESETS", "").strip()) if os.getenv("AGENTBUS_FEATURE_PRESETS") else None,
        root / "config" / "feature_presets.yaml",
        root / "feature_presets.yaml",
    ):
        if cand is None:
            continue
        if cand.is_file():
            return cand
    return None


def list_presets() -> list[dict[str, Any]]:
    """[{name, description, features}]."""
    path = _presets_path()
    if path is None:
        return []
    try:
        import yaml
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        logger.warning("presets load failed: %s", exc)
        return []
    section = data.get("presets") if isinstance(data, dict) else {}
    if not isinstance(section, dict):
        return []
    out: list[dict[str, Any]] = []
    for name, body in section.items():
        if not isinstance(body, dict):
            continue
        feats = body.get("features") if isinstance(body.get("features"), dict) else {}
        env = body.get("env") if isinstance(body.get("env"), dict) else {}
        out.append({
            "name": str(name),
            "description": str(body.get("description") or ""),
            "features": {str(k): _coerce_bool(v) for k, v in feats.items()},
            "env": {str(k): str(v) for k, v in env.items()},
        })
    return out


def apply_preset(name: str, *, save: bool = True) -> dict[str, bool]:
    """Apply named preset to in-memory flags; optionally persist YAML.

    Returns resulting flags. Unknown preset → ValueError.
    """
    global _FLAGS
    presets = {p["name"]: p for p in list_presets()}
    key = (name or "").strip().lower().replace("-", "_")
    # allow night-autonomous alias
    aliases = {
        "night": "night_autonomous",
        "night_autonomous": "night_autonomous",
        "beginner": "beginner_ru",
        "beginner_ru": "beginner_ru",
        "ru": "beginner_ru",
    }
    key = aliases.get(key, key)
    if key not in presets:
        raise ValueError(f"unknown preset: {name!r}; known={sorted(presets)}")
    body = presets[key]
    flags = get_flags()
    for feat, val in (body.get("features") or {}).items():
        flags[str(feat).lower()] = bool(val)
    _FLAGS = flags
    # Optional env overrides from preset (e.g. beginner_ru parallel=1)
    env_map = body.get("env") or {}
    if isinstance(env_map, dict):
        for ek, ev in env_map.items():
            if not ek:
                continue
            try:
                os.environ[str(ek)] = str(ev)
            except Exception:
                pass
    try:
        from core.plugin_registry import clear_cache
        clear_cache()
    except Exception:
        pass
    if save:
        save_flags()
    return dict(_FLAGS)


# Convenience aliases matching yaml keys
def conversation_enabled() -> bool:
    return is_enabled("conversation")


def skills_enabled() -> bool:
    return is_enabled("skills")


def cache_enabled() -> bool:
    return is_enabled("solution_cache")


def autopilot_enabled() -> bool:
    return is_enabled("autopilot")


def rag_enabled() -> bool:
    return is_enabled("codebase_rag")

def list_flags() -> dict[str, bool]:
    """Текущие значения всех известных флагов."""
    try:
        reload_flags()
    except Exception:
        pass
    return {name: is_enabled(name, default=_DEFAULTS.get(name, True)) for name in KNOWN_FEATURES}



