# -*- coding: utf-8 -*-
"""FC-37C Session bootstrap — quick analysis when a session/project opens.

Called from UI (chat_panel project change) or CLI session start.
Never blocks fatally; never mutates LivingPlan.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


def _env_flag(name: str, default: bool = True) -> bool:
    raw = os.getenv(name, "").strip().lower()
    if not raw:
        return default
    return raw not in ("0", "false", "no", "off")


@dataclass
class SessionBootstrapResult:
    """What was prepared for the new session."""

    project_root: str = ""
    banner: str = ""
    analysis_summary: str = ""
    advice_lines: list[str] = field(default_factory=list)
    kind: str = ""
    skipped: bool = False
    reason: str = ""
    duration_ms: float = 0.0
    cached: bool = False
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def format_human(self) -> str:
        if self.skipped:
            return f"Session bootstrap skipped: {self.reason or 'n/a'}"
        parts = [self.banner or self.analysis_summary or "Session ready."]
        return "\n".join(p for p in parts if p).strip()


def _cache_path(root: Path) -> Path:
    return root / ".agentbus" / "session_bootstrap_cache.json"


def _read_cache(root: Path, max_age_sec: float) -> dict[str, Any] | None:
    path = _cache_path(root)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        ts = float(data.get("scanned_at") or 0)
        if max_age_sec > 0 and (time.time() - ts) > max_age_sec:
            return None
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return None


def _write_cache(root: Path, payload: dict[str, Any]) -> None:
    path = _cache_path(root)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)
    except OSError:
        pass


def bootstrap_session(
    project_root: str | Path,
    *,
    force: bool = False,
    use_cache: bool = True,
    cache_ttl_sec: float | None = None,
    use_index: bool = False,
    advice_limit: int = 3,
    push_risks_to_state: bool = False,
    state: Any | None = None,
) -> SessionBootstrapResult:
    """Run quick scan + advisor banner for session/project open.

    Env:
      AGENTBUS_SESSION_SCAN=0  → skip
      AGENTBUS_SESSION_SCAN_TTL=3600  → cache seconds (default 1h)
    """
    t0 = time.time()
    root = Path(project_root).resolve()

    if not _env_flag("AGENTBUS_SESSION_SCAN", True) and not force:
        return SessionBootstrapResult(
            project_root=str(root),
            skipped=True,
            reason="AGENTBUS_SESSION_SCAN disabled",
            duration_ms=(time.time() - t0) * 1000,
        )

    if not root.is_dir():
        return SessionBootstrapResult(
            project_root=str(root),
            skipped=True,
            reason="project root not a directory",
            duration_ms=(time.time() - t0) * 1000,
        )

    ttl = cache_ttl_sec
    if ttl is None:
        try:
            ttl = float(os.getenv("AGENTBUS_SESSION_SCAN_TTL", "3600"))
        except ValueError:
            ttl = 3600.0

    if use_cache and not force:
        cached = _read_cache(root, float(ttl or 0))
        if cached:
            return SessionBootstrapResult(
                project_root=str(root),
                banner=str(cached.get("banner") or ""),
                analysis_summary=str(cached.get("analysis_summary") or ""),
                advice_lines=list(cached.get("advice_lines") or []),
                kind=str(cached.get("kind") or ""),
                cached=True,
                duration_ms=(time.time() - t0) * 1000,
                meta={"cache_age_sec": time.time() - float(cached.get("scanned_at") or time.time())},
            )

    try:
        from intelligence.development_advisor import advise
        from intelligence.project_analysis import apply_analysis_to_state, quick_scan
    except Exception as exp:
        return SessionBootstrapResult(
            project_root=str(root),
            skipped=True,
            reason=f"import: {exp}",
            duration_ms=(time.time() - t0) * 1000,
        )

    try:
        report = quick_scan(root, state=state, use_index=use_index)
        adv = advise(report=report, state=state, limit=advice_limit)
    except Exception as exp:
        return SessionBootstrapResult(
            project_root=str(root),
            skipped=True,
            reason=f"scan: {exp}",
            duration_ms=(time.time() - t0) * 1000,
        )

    if push_risks_to_state and state is not None:
        try:
            apply_analysis_to_state(report, state)
        except Exception:
            pass

    advice_lines = [f"{a.rank}. {a.title}" for a in adv.advice]
    banner = adv.format_human()
    result = SessionBootstrapResult(
        project_root=str(root),
        banner=banner,
        analysis_summary=adv.situation or report.summary,
        advice_lines=advice_lines,
        kind=report.kind,
        duration_ms=(time.time() - t0) * 1000,
        meta={
            "py_files": report.py_files,
            "test_files": report.test_files,
            "opportunities": len(report.opportunities),
        },
    )

    if use_cache:
        _write_cache(root, {
            "scanned_at": time.time(),
            "banner": result.banner,
            "analysis_summary": result.analysis_summary,
            "advice_lines": result.advice_lines,
            "kind": result.kind,
        })

    return result


def bootstrap_banner(project_root: str | Path, **kwargs: Any) -> str:
    """Convenience: only the human text for chat system note."""
    return bootstrap_session(project_root, **kwargs).format_human()
