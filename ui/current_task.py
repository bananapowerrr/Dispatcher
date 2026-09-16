# -*- coding: utf-8 -*-
"""FC-06: pure helpers for current-task strip (no CustomTkinter required for tests)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def find_active_task(root: Path, pending_ids: set[str] | None = None) -> dict[str, Any] | None:
    """Best active task: processing JSON, else newest pending spill."""
    root = Path(root)
    candidates: list[tuple[float, dict[str, Any]]] = []
    channels = root / "channels"
    if channels.is_dir():
        for d in channels.glob("*/processing"):
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
                    data["_path"] = str(f)
                    data["_state"] = "processing"
                    mtime = f.stat().st_mtime
                    candidates.append((mtime, data))
            except OSError:
                continue
    if not candidates and pending_ids:
        spill = root / ".agentbus" / "desktop_queue"
        if spill.is_dir():
            for tid in pending_ids:
                f = spill / f"{tid}.json"
                if not f.is_file():
                    continue
                try:
                    data = json.loads(f.read_text(encoding="utf-8"))
                    if isinstance(data, dict):
                        data["_path"] = str(f)
                        data["_state"] = "queued"
                        candidates.append((f.stat().st_mtime, data))
                except Exception:
                    continue
    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]


def format_current_task(row: dict[str, Any] | None) -> str:
    """One/ multi-line strip for sidebar or phase area."""
    if not row:
        return "Нет активной задачи"
    tid = str(row.get("id") or "")[:12]
    state = str(row.get("_state") or row.get("status") or "").lower()
    msg = str(row.get("message") or "").replace("\n", " ")[:80]
    phase = str(row.get("phase") or "")
    if not phase and isinstance(row.get("metadata"), dict):
        phase = str(row["metadata"].get("phase") or "")
    lines = []
    if state in ("processing", "claimed"):
        lines.append(f"● В работе {tid}" + (f" · {phase}" if phase else ""))
    elif state in ("queued", "pending", "incoming"):
        lines.append(f"○ В очереди {tid}")
    else:
        lines.append(f"{state or '?'} {tid}")
    if msg:
        lines.append(msg)
    try:
        from core.task_result import build_task_result, history_card_lines

        card = history_card_lines(row)
        if card.get("meta"):
            lines.append(card["meta"])
        if card.get("verify"):
            lines.append(card["verify"])
        if card.get("files"):
            lines.append(card["files"])
    except Exception:
        pass
    return "\n".join(lines)
