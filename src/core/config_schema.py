# -*- coding: utf-8 -*-
"""Offline config shape validation (no network, no Ollama).

Validates workers.yaml / providers.yaml / feature_flags.yaml structure so
misconfigured installs fail early in doctor / --diagnose, not mid-task.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class SchemaIssue:
    path: str
    message: str
    level: str = "error"  # error | warn


@dataclass
class SchemaReport:
    issues: list[SchemaIssue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not any(i.level == "error" for i in self.issues)

    def add(self, path: str, message: str, *, level: str = "error") -> None:
        self.issues.append(SchemaIssue(path, message, level))


def _load_yaml(path: Path) -> Any:
    try:
        import yaml
    except ImportError as e:
        raise RuntimeError("PyYAML required for config validation") from e
    text = path.read_text(encoding="utf-8")
    return yaml.safe_load(text)


def validate_workers(data: Any, *, path: str = "workers.yaml") -> SchemaReport:
    rep = SchemaReport()
    if data is None:
        rep.add(path, "empty file")
        return rep
    if not isinstance(data, list):
        rep.add(path, f"root must be a list of workers, got {type(data).__name__}")
        return rep
    names: set[str] = set()
    for i, item in enumerate(data):
        loc = f"{path}[{i}]"
        if not isinstance(item, dict):
            rep.add(loc, "worker must be a mapping")
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            rep.add(loc, "missing name")
        elif name in names:
            rep.add(loc, f"duplicate worker name: {name}")
        else:
            names.add(name)
        for key in ("harness", "provider"):
            if not str(item.get(key) or "").strip():
                rep.add(loc, f"missing {key}", level="warn")
        # command optional for native-only profiles
        if "timeout" in item:
            try:
                t = int(item["timeout"])
                if t < 15:
                    rep.add(loc, f"timeout too small: {t}", level="warn")
            except (TypeError, ValueError):
                rep.add(loc, "timeout must be int")
        if "tier" in item:
            try:
                tier = int(item["tier"])
                if not 1 <= tier <= 10:
                    rep.add(loc, f"tier out of range 1..10: {tier}", level="warn")
            except (TypeError, ValueError):
                rep.add(loc, "tier must be int", level="warn")
        if "complexity" in item:
            try:
                c = int(item["complexity"])
                if not 1 <= c <= 5:
                    rep.add(loc, f"complexity out of range 1..5: {c}", level="warn")
            except (TypeError, ValueError):
                rep.add(loc, "complexity must be int", level="warn")
    if not names:
        rep.add(path, "no workers defined")
    return rep


def validate_providers(data: Any, *, path: str = "providers.yaml") -> SchemaReport:
    rep = SchemaReport()
    if data is None:
        rep.add(path, "empty file")
        return rep
    if not isinstance(data, list):
        rep.add(path, f"root must be a list of providers, got {type(data).__name__}")
        return rep
    ids: set[str] = set()
    for i, item in enumerate(data):
        loc = f"{path}[{i}]"
        if not isinstance(item, dict):
            rep.add(loc, "provider must be a mapping")
            continue
        pid = str(item.get("id") or "").strip()
        if not pid:
            rep.add(loc, "missing id")
        elif pid in ids:
            rep.add(loc, f"duplicate provider id: {pid}")
        else:
            ids.add(pid)
        if not str(item.get("type") or "").strip():
            rep.add(loc, "missing type", level="warn")
        models = item.get("models")
        if models is not None and not isinstance(models, list):
            rep.add(loc, "models must be a list")
    if not ids:
        rep.add(path, "no providers defined")
    return rep


def validate_feature_flags(data: Any, *, path: str = "feature_flags.yaml") -> SchemaReport:
    rep = SchemaReport()
    if data is None:
        rep.add(path, "empty file", level="warn")
        return rep
    if not isinstance(data, dict):
        rep.add(path, f"root must be a mapping, got {type(data).__name__}")
        return rep
    features = data.get("features", data)
    if not isinstance(features, dict):
        rep.add(path, "features must be a mapping")
        return rep
    for key, val in features.items():
        if not isinstance(val, (bool, int)):
            rep.add(f"{path}.features.{key}", f"expected bool, got {type(val).__name__}", level="warn")
    return rep


def validate_file(path: Path, kind: str) -> SchemaReport:
    """kind: workers | providers | feature_flags"""
    if not path.is_file():
        rep = SchemaReport()
        rep.add(str(path), "file not found")
        return rep
    try:
        data = _load_yaml(path)
    except Exception as e:
        rep = SchemaReport()
        rep.add(str(path), f"parse error: {e}")
        return rep
    if kind == "workers":
        return validate_workers(data, path=str(path))
    if kind == "providers":
        return validate_providers(data, path=str(path))
    if kind == "feature_flags":
        return validate_feature_flags(data, path=str(path))
    rep = SchemaReport()
    rep.add(str(path), f"unknown kind: {kind}")
    return rep


def validate_project_configs(root: Path | None = None) -> SchemaReport:
    """Validate default AgentBus config files under root/config."""
    root = Path(root) if root else Path.cwd()
    cfg = root / "config"
    merged = SchemaReport()
    mapping = (
        (cfg / "workers.yaml", "workers"),
        (cfg / "providers.yaml", "providers"),
        (cfg / "feature_flags.yaml", "feature_flags"),
    )
    for path, kind in mapping:
        if not path.is_file():
            # try core.config paths later; warn only
            merged.add(str(path), "missing", level="warn")
            continue
        sub = validate_file(path, kind)
        merged.issues.extend(sub.issues)
    return merged


def format_report(rep: SchemaReport) -> str:
    if not rep.issues:
        return "config schema: OK"
    lines = []
    for i in rep.issues:
        lines.append(f"[{i.level}] {i.path}: {i.message}")
    return "\n".join(lines)
