# -*- coding: utf-8 -*-
"""FC-07: read last terminal TaskResult from channels/*/done|errors (no GUI).

Used by workers_panel / skills_panel for product read-only status.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def iter_terminal_json(root: Path, limit: int = 40) -> list[tuple[float, Path, dict[str, Any]]]:
    """Newest terminal task JSON under channels/*/done and channels/*/errors."""
    root = Path(root)
    found: list[tuple[float, Path, dict[str, Any]]] = []
    channels = root / "channels"
    if not channels.is_dir():
        return []
    for state in ("done", "errors"):
        for d in channels.glob(f"*/{state}"):
            try:
                for f in d.glob("*.json"):
                    if f.name.endswith(".lease.json"):
                        continue
                    try:
                        data = json.loads(f.read_text(encoding="utf-8"))
                    except Exception:
                        continue
                    if not isinstance(data, dict):
                        continue
                    try:
                        mtime = f.stat().st_mtime
                    except OSError:
                        continue
                    found.append((mtime, f, data))
            except OSError:
                continue
    found.sort(key=lambda x: x[0], reverse=True)
    return found[: max(1, limit)]


def last_task_result(root: Path) -> dict[str, Any] | None:
    """Return build_task_result(...).to_dict() for newest terminal task, or None."""
    rows = iter_terminal_json(root, limit=5)
    if not rows:
        return None
    _, path, data = rows[0]
    try:
        from core.task_result import build_task_result

        tr = build_task_result(data)
        out = tr.to_dict()
        out["_path"] = str(path)
        return out
    except Exception:
        return {
            "task_id": str(data.get("id") or path.stem),
            "status": str(data.get("status") or path.parent.name).upper(),
            "ok": path.parent.name == "done",
            "summary": str((data.get("result") or {}).get("summary") or "")[:300],
            "_path": str(path),
        }


def last_outcomes_by_worker(root: Path, limit: int = 30) -> dict[str, dict[str, Any]]:
    """Map worker_name → latest TaskResult dict (read-only product view)."""
    by_w: dict[str, dict[str, Any]] = {}
    for _mtime, path, data in iter_terminal_json(root, limit=limit):
        try:
            from core.task_result import build_task_result

            tr = build_task_result(data)
            w = (tr.worker or "").strip() or "unknown"
            if w in by_w:
                continue
            d = tr.to_dict()
            d["_path"] = str(path)
            by_w[w] = d
        except Exception:
            continue
    return by_w


def last_skill_outcomes(root: Path, limit: int = 30) -> dict[str, dict[str, Any]]:
    """Map skill_name → latest TaskResult where skill was used."""
    by_s: dict[str, dict[str, Any]] = {}
    for _mtime, path, data in iter_terminal_json(root, limit=limit):
        try:
            from core.task_result import build_task_result

            tr = build_task_result(data)
            s = (tr.skill or "").strip()
            if not s or s in by_s:
                continue
            d = tr.to_dict()
            d["_path"] = str(path)
            by_s[s] = d
        except Exception:
            continue
    return by_s


def format_worker_line(tr: dict[str, Any] | None) -> str:
    if not tr:
        return "нет данных"
    mark = "✓" if tr.get("ok") else "✗"
    st = tr.get("status") or "?"
    dur = tr.get("duration_sec") or 0
    sum_ = (tr.get("summary") or "")[:60]
    tid = str(tr.get("task_id") or "")[:10]
    bits = [f"{mark} {st}", tid]
    if dur:
        bits.append(f"{float(dur):.0f}s")
    if sum_:
        bits.append(sum_)
    return " · ".join(bits)
