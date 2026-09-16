# -*- coding: utf-8 -*-
"""File Sentinel — quarantine junk, protect imported modules, promote *_v2 shadows.

Never hard-deletes project files: moves suspects into .agentbus/quarantine/<ts>/.
"""
from __future__ import annotations

import ast
import os
import re
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable


JUNK_SUFFIXES = {
    ".log", ".tmp", ".bak", ".swp", ".pyc", ".pyo", ".orig", ".rej",
}
JUNK_NAMES = {
    "thumbs.db", ".ds_store", "desktop.ini",
}
SHADOW_RE = re.compile(
    r"^(?P<stem>.+?)(?:__v2|_v2|_new|_fixed|_refactored)(?P<suffix>\.[^.]+)$",
    re.I,
)


def sentinel_enabled() -> bool:
    return os.getenv("AGENTBUS_FILE_SENTINEL", "1").strip().lower() not in (
        "0", "false", "no", "off",
    )


@dataclass
class QuarantineAction:
    src: str
    dst: str
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {"src": self.src, "dst": self.dst, "reason": self.reason}


@dataclass
class ShadowCandidate:
    shadow: str
    target: str
    syntax_ok: bool
    imported: bool = False
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "shadow": self.shadow,
            "target": self.target,
            "syntax_ok": self.syntax_ok,
            "imported": self.imported,
            "notes": self.notes,
        }


@dataclass
class SentinelReport:
    quarantined: list[QuarantineAction] = field(default_factory=list)
    protected: list[str] = field(default_factory=list)
    shadows: list[ShadowCandidate] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "quarantined": [q.to_dict() for q in self.quarantined],
            "protected": list(self.protected),
            "shadows": [s.to_dict() for s in self.shadows],
        }


class FileSentinel:
    def __init__(self, project_root: str | Path) -> None:
        self.root = Path(project_root).resolve()
        self.quarantine_root = self.root / ".agentbus" / "quarantine"

    def _qdir(self) -> Path:
        d = self.quarantine_root / time.strftime("%Y%m%d_%H%M%S")
        d.mkdir(parents=True, exist_ok=True)
        return d

    def is_junk(self, path: Path) -> bool:
        name = path.name.lower()
        if name in JUNK_NAMES:
            return True
        if path.suffix.lower() in JUNK_SUFFIXES:
            return True
        if name.endswith(".log") or name.startswith("core."):
            return True
        return False

    def collect_imports(self, paths: Iterable[Path] | None = None) -> set[str]:
        """Module basenames imported anywhere under project (best-effort)."""
        imported: set[str] = set()
        roots = list(paths) if paths is not None else list(self.root.rglob("*.py"))
        for p in roots:
            try:
                if not p.is_file() or ".agentbus" in p.parts or "venv" in p.parts:
                    continue
                if any(x.startswith(".") for x in p.parts if x not in (".",)):
                    # allow .agentbus skip already
                    pass
                tree = ast.parse(p.read_text(encoding="utf-8", errors="replace"))
            except Exception:
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for a in node.names:
                        imported.add(a.name.split(".")[0])
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imported.add(node.module.split(".")[0])
        return imported

    def is_protected(self, path: Path, imported: set[str] | None = None) -> bool:
        """True if basename (sans suffix) is imported by other modules."""
        if imported is None:
            imported = self.collect_imports()
        stem = path.stem
        # foo_v2.py → still protect if "foo_v2" imported
        if stem in imported or path.name in imported:
            return True
        # package __init__ always protected
        if path.name == "__init__.py":
            return True
        return False

    def quarantine(self, path: Path, reason: str) -> QuarantineAction | None:
        path = path.resolve()
        try:
            path.relative_to(self.root)
        except ValueError:
            return None
        if not path.exists():
            return None
        dest_dir = self._qdir()
        rel = path.relative_to(self.root)
        dest = dest_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.move(str(path), str(dest))
        except OSError:
            try:
                shutil.copy2(str(path), str(dest))
                path.unlink()
            except OSError:
                return None
        return QuarantineAction(src=str(rel), dst=str(dest.relative_to(self.root)), reason=reason)

    def scan_and_quarantine_junk(
        self,
        paths: list[str | Path] | None = None,
        *,
        untracked_only: bool = False,
    ) -> SentinelReport:
        """Move junk files to quarantine. Never touches protected imports."""
        report = SentinelReport()
        if not sentinel_enabled():
            return report
        imported = self.collect_imports()
        candidates: list[Path] = []
        if paths:
            for raw in paths:
                p = Path(raw)
                if not p.is_file():
                    p = self.root / p
                if p.is_file():
                    candidates.append(p)
        else:
            # limited scan: .agentbus tmp + root-level junk only (safe default)
            for p in self.root.iterdir():
                if p.is_file() and self.is_junk(p):
                    candidates.append(p)
            tmp = self.root / ".agentbus" / "tmp"
            if tmp.is_dir():
                candidates.extend(x for x in tmp.rglob("*") if x.is_file())

        for p in candidates:
            if not self.is_junk(p):
                continue
            if self.is_protected(p, imported):
                report.protected.append(str(p.relative_to(self.root)) if p.is_relative_to(self.root) else str(p))
                continue
            action = self.quarantine(p, reason="junk")
            if action:
                report.quarantined.append(action)
        return report

    def find_shadows(self, paths: list[str | Path] | None = None) -> list[ShadowCandidate]:
        """Detect * _v2 / _new companions next to originals."""
        from safety.syntax_guard import check_file

        shadows: list[ShadowCandidate] = []
        imported = self.collect_imports()
        files: list[Path] = []
        if paths:
            for raw in paths:
                p = Path(raw)
                if not p.is_file():
                    p = self.root / p
                if p.is_file():
                    files.append(p)
        else:
            files = [p for p in self.root.rglob("*.py") if ".agentbus" not in p.parts and "venv" not in p.parts][:500]

        for p in files:
            m = SHADOW_RE.match(p.name)
            if not m:
                continue
            target = p.with_name(m.group("stem") + m.group("suffix"))
            issue = check_file(p)
            shadows.append(
                ShadowCandidate(
                    shadow=str(p.relative_to(self.root)) if p.is_relative_to(self.root) else str(p),
                    target=str(target.relative_to(self.root)) if target.is_relative_to(self.root) else str(target),
                    syntax_ok=issue is None,
                    imported=self.is_protected(p, imported),
                    notes="" if issue is None else issue.format(),
                )
            )
        return shadows

    def promote_shadow(
        self,
        shadow_rel: str,
        *,
        dry_run: bool = True,
    ) -> dict[str, Any]:
        """Replace original with shadow after syntax check. Default dry_run."""
        from safety.syntax_guard import check_file

        shadow = self.root / shadow_rel
        m = SHADOW_RE.match(shadow.name)
        if not m or not shadow.is_file():
            return {"ok": False, "error": "not a shadow file or missing"}
        target = shadow.with_name(m.group("stem") + m.group("suffix"))
        issue = check_file(shadow)
        if issue:
            return {"ok": False, "error": issue.format()}
        if dry_run:
            return {
                "ok": True,
                "dry_run": True,
                "shadow": shadow_rel,
                "target": str(target.relative_to(self.root)),
            }
        # backup original to quarantine, then copy shadow → target
        if target.is_file():
            self.quarantine(target, reason="shadow_promote_backup")
        try:
            shutil.copy2(str(shadow), str(target))
            self.quarantine(shadow, reason="shadow_promoted_cleanup")
        except OSError as exc:
            return {"ok": False, "error": str(exc)}
        return {
            "ok": True,
            "dry_run": False,
            "shadow": shadow_rel,
            "target": str(target.relative_to(self.root)),
        }

    def scan(self, paths: list[str | Path] | None = None) -> SentinelReport:
        report = self.scan_and_quarantine_junk(paths)
        report.shadows = self.find_shadows(paths)
        return report
