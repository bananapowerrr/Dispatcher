# -*- coding: utf-8 -*-
"""Per-run diagnostics under ``.agentbus/runs/<run_id>/``.

Offline-safe: no network, no LLM. Used by live_smoke and (optionally) runtime.

Layout::

    .agentbus/runs/2026-09-24_21-43-12_a81f3c/
        run.json
        events.jsonl
        result.json
        summary.md
        diff.patch          # optional
        worker.log          # optional
        verify.log          # optional
"""
from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any


def make_run_id(ts: float | None = None) -> str:
    """Human-sortable unique id: YYYY-MM-DD_HH-MM-SS_<6hex>."""
    t = time.localtime(ts if ts is not None else time.time())
    stamp = time.strftime("%Y-%m-%d_%H-%M-%S", t)
    return f"{stamp}_{uuid.uuid4().hex[:6]}"


@dataclass
class RunSession:
    """Write structured artifacts for one acceptance/smoke run."""

    project_root: Path
    run_id: str = field(default_factory=make_run_id)
    meta: dict[str, Any] = field(default_factory=dict)
    _events: list[dict[str, Any]] = field(default_factory=list, repr=False)

    def __post_init__(self) -> None:
        self.project_root = Path(self.project_root)
        self.dir.mkdir(parents=True, exist_ok=True)
        self._write_run_json(status="started")

    @property
    def dir(self) -> Path:
        return self.project_root / ".agentbus" / "runs" / self.run_id

    def event(self, name: str, **detail: Any) -> None:
        row = {
            "ts": time.time(),
            "name": str(name),
            "detail": {k: _jsonable(v) for k, v in detail.items()},
        }
        self._events.append(row)
        path = self.dir / "events.jsonl"
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")

    def write_text(self, name: str, content: str) -> Path:
        path = self.dir / name
        path.write_text(content or "", encoding="utf-8")
        return path

    def write_json(self, name: str, data: Any) -> Path:
        path = self.dir / name
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2, default=str) + "\n",
            encoding="utf-8",
        )
        return path

    def finish(
        self,
        *,
        final_status: str,
        result: dict[str, Any] | None = None,
        task: str = "",
        worker: str = "",
        duration_sec: float | None = None,
        attempts: int = 1,
        files_changed: list[str] | None = None,
        verification: dict[str, Any] | None = None,
        error: str = "",
        events: list[str] | None = None,
        warnings: list[str] | None = None,
    ) -> Path:
        """Write result.json + summary.md and close run.json."""
        payload = {
            "run_id": self.run_id,
            "final_status": final_status,
            "task": (task or "")[:500],
            "worker": worker or "",
            "duration_sec": duration_sec,
            "attempts": attempts,
            "files_changed": list(files_changed or [])[:50],
            "verification": verification or {},
            "error": (error or "")[:2000],
            "events": list(events or []),
            "warnings": list(warnings or []),
            "result": result or {},
            "meta": dict(self.meta),
        }
        self.write_json("result.json", payload)
        summary = render_summary_md(payload)
        self.write_text("summary.md", summary)
        self._write_run_json(status="finished", final_status=final_status)
        return self.dir / "summary.md"

    def _write_run_json(self, **extra: Any) -> None:
        data = {
            "run_id": self.run_id,
            "project_root": str(self.project_root),
            "started_ts": self.meta.get("started_ts") or time.time(),
            **self.meta,
            **extra,
        }
        if "started_ts" not in self.meta:
            self.meta["started_ts"] = data["started_ts"]
        self.write_json("run.json", data)


def _jsonable(v: Any) -> Any:
    if isinstance(v, (str, int, float, bool)) or v is None:
        return v
    if isinstance(v, Path):
        return str(v)
    if isinstance(v, (list, tuple)):
        return [_jsonable(x) for x in v[:50]]
    if isinstance(v, dict):
        return {str(k): _jsonable(val) for k, val in list(v.items())[:40]}
    return str(v)[:500]


def render_summary_md(payload: dict[str, Any]) -> str:
    """Human report for GitHub/audit (GPT acceptance format)."""
    rid = payload.get("run_id") or "?"
    status = str(payload.get("final_status") or "?").upper()
    lines = [
        f"# RUN {rid}",
        "",
        f"**Final:** `{status}`",
        "",
        "## Task",
        "",
        f"> {payload.get('task') or '(none)'}",
        "",
        "## Worker",
        "",
        f"- worker: `{payload.get('worker') or '—'}`",
        f"- duration: {payload.get('duration_sec') if payload.get('duration_sec') is not None else '—'}",
        f"- attempts: {payload.get('attempts') or 1}",
        "",
        "## Files changed",
        "",
    ]
    files = payload.get("files_changed") or []
    if files:
        for f in files:
            lines.append(f"- `{f}`")
    else:
        lines.append("- (none recorded)")
    lines.extend(["", "## Verification", ""])
    ver = payload.get("verification") or {}
    if ver:
        for k, v in ver.items():
            lines.append(f"- **{k}:** {v}")
    else:
        lines.append("- (no payload)")
    lines.extend(["", "## Events", ""])
    for ev in payload.get("events") or []:
        lines.append(f"- `{ev}`")
    if not payload.get("events"):
        lines.append("- (none)")
    warns = payload.get("warnings") or []
    if warns:
        lines.extend(["", "## Warnings", ""])
        for w in warns:
            lines.append(f"- {w}")
    err = payload.get("error") or ""
    if err:
        lines.extend(["", "## Error", "", "```", err[:1500], "```"])
    lines.append("")
    return "\n".join(lines)


def latest_run_dir(project_root: str | Path) -> Path | None:
    root = Path(project_root) / ".agentbus" / "runs"
    if not root.is_dir():
        return None
    dirs = [d for d in root.iterdir() if d.is_dir()]
    if not dirs:
        return None
    return max(dirs, key=lambda p: p.stat().st_mtime)
