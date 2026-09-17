# -*- coding: utf-8 -*-
"""FC-17: Queue visibility — desktop FIFO + file-bus states."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from ui.paths import agentbus_root


def _t(key: str, default: str = "") -> str:
    try:
        from ui.i18n_ui import t as _tr
        return _tr(key, default=default)
    except Exception:
        return default


def _mtime(p: Path) -> float:
    try:
        return p.stat().st_mtime
    except OSError:
        return 0.0


def _read_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            data["_path"] = str(path)
            data["_mtime"] = _mtime(path)
            return data
    except Exception:
        pass
    return {"id": path.stem, "message": path.name, "_path": str(path), "_mtime": _mtime(path)}


def collect_queue_snapshot(limit: int = 40) -> dict[str, Any]:
    """Pure data for queue UI (no toolkit)."""
    base = agentbus_root()
    counts = {
        "desktop": 0,
        "incoming": 0,
        "processing": 0,
        "deferred": 0,
        "done": 0,
        "errors": 0,
    }
    items: list[dict] = []

    try:
        from core.local_queue import get_local_queue
        counts["desktop"] = int(get_local_queue(base).size())
    except Exception:
        pass
    spill = base / ".agentbus" / "desktop_queue"
    if spill.is_dir():
        try:
            spill_files = list(spill.glob("*.json"))
            if not counts["desktop"]:
                counts["desktop"] = len(spill_files)
            for f in sorted(spill_files, key=_mtime, reverse=True):
                data = _read_json(f)
                data["_state"] = str(data.get("status") or "queued").lower()
                data["_channel"] = "desktop"
                items.append(data)
        except OSError:
            pass

    root = base / "channels"
    if root.is_dir():
        for state in ("incoming", "processing", "deferred", "done", "errors"):
            for d in root.glob(f"*/{state}"):
                try:
                    files = [p for p in d.glob("*.json") if not p.name.endswith(".lease.json")]
                    counts[state] += len(files)
                    if state in ("incoming", "processing", "deferred"):
                        for f in sorted(files, key=_mtime, reverse=True)[:15]:
                            data = _read_json(f)
                            data["_state"] = state
                            data["_channel"] = d.parent.name
                            items.append(data)
                except OSError:
                    continue

    seen: set[str] = set()
    uniq: list[dict] = []
    for it in items:
        key = str(it.get("id") or it.get("_path") or "")
        if key in seen:
            continue
        seen.add(key)
        uniq.append(it)
    uniq.sort(key=lambda x: float(x.get("_mtime") or 0), reverse=True)
    return {"counts": counts, "items": uniq[:limit]}


def format_queue_summary(counts: dict | None) -> str:
    """FC-21: i18n queue summary."""
    try:
        from ui.status_labels import format_queue_counts
        return format_queue_counts(counts)
    except Exception:
        c = counts or {}
        return (
            f"queued={c.get('queued', c.get('pending', 0))} "
            f"run={c.get('processing', 0)} "
            f"def={c.get('deferred', 0)} "
            f"err={c.get('errors', 0)}"
        )


def _build_queue_panel_class():
    import customtkinter as ctk

    class QueuePanel(ctk.CTkFrame):
        """Live queue list for desktop + file-bus."""

        def __init__(self, parent, poll_ms: int = 3000, on_select=None):
            super().__init__(parent)
            self.poll_ms = poll_ms
            self.on_select = on_select

            top = ctk.CTkFrame(self, fg_color="transparent")
            top.pack(fill="x", padx=8, pady=4)
            ctk.CTkLabel(
                top,
                text=_t("queue_title", default="Очередь задач"),
                font=ctk.CTkFont(size=14, weight="bold"),
            ).pack(side="left")
            ctk.CTkButton(
                top, text=_t("refresh", default="Обновить"), width=90, command=self.refresh
            ).pack(side="right")

            self.summary = ctk.CTkLabel(self, text="—", anchor="w", text_color="gray")
            self.summary.pack(fill="x", padx=12, pady=(0, 4))

            self.scroll = ctk.CTkScrollableFrame(self)
            self.scroll.pack(fill="both", expand=True, padx=8, pady=8)

            self.after(300, self.refresh)
            self.after(self.poll_ms, self._tick)

        def refresh(self) -> None:
            def work():
                return collect_queue_snapshot()

            def apply(snap):
                for w in self.scroll.winfo_children():
                    w.destroy()
                snap = snap or {}
                counts = snap.get("counts") or {}
                items = snap.get("items") or []
                try:
                    self.summary.configure(text=format_queue_summary(counts))
                except Exception:
                    pass
                if not items:
                    try:
                        from app.facade import AppFacade
                        empty = AppFacade().empty_message("queue")
                    except Exception:
                        empty = _t("queue_empty", default="Очередь пуста")
                    ctk.CTkLabel(
                        self.scroll,
                        text=empty,
                        text_color="gray",
                    ).pack(anchor="w", padx=8, pady=(16, 4))
                    ctk.CTkLabel(
                        self.scroll,
                        text=_t(
                            "queue_empty_hint",
                            default="Напиши в чат или Ctrl+K → Composer",
                        ),
                        text_color="gray",
                    ).pack(anchor="w", padx=8, pady=(0, 16))
                    return
                for row in items:
                    self._render_row(row)

            try:
                from ui.async_poll import run_bg
                run_bg(self, work, apply, coalesce_key="queue")
            except Exception:
                apply(work())

        def _render_row(self, row: dict) -> None:
            state = str(row.get("_state") or "").lower()
            colors = {
                "queued": "#90caf9",
                "pending": "#90caf9",
                "incoming": "#90caf9",
                "processing": "#ffe0b2",
                "running": "#ffe0b2",
                "deferred": "#ce93d8",
                "done": "#a5d6a7",
                "errors": "#ef9a9a",
                "error": "#ef9a9a",
            }
            fg = colors.get(state, "gray70")
            frame = ctk.CTkFrame(self.scroll)
            frame.pack(fill="x", pady=2)
            full_tid = str(row.get("id") or "")
            def _click(_e=None, _tid=full_tid):
                if self.on_select and _tid:
                    try:
                        self.on_select(_tid)
                    except Exception:
                        pass
            try:
                frame.bind("<Button-1>", _click)
            except Exception:
                pass
            tid = full_tid[:16]
            ch = str(row.get("_channel") or "")
            ch_disp = "ПК" if ch == "desktop" else ch
            head = f"{state or '—'}  {tid}  · {ch_disp}"
            ctk.CTkLabel(frame, text=head, text_color=fg, anchor="w").pack(
                fill="x", padx=8, pady=(4, 0)
            )
            msg = str(row.get("message") or "")[:120].replace("\n", " ")
            if msg:
                ctk.CTkLabel(frame, text=msg, anchor="w", text_color="gray").pack(
                    fill="x", padx=8, pady=(0, 4)
                )
            try:
                ts = float(row.get("_mtime") or 0)
                if ts:
                    tstr = datetime.fromtimestamp(ts).strftime("%H:%M:%S")
                    ctk.CTkLabel(frame, text=tstr, text_color="gray", anchor="e").pack(
                        fill="x", padx=8, pady=(0, 2)
                    )
            except Exception:
                pass

        def _tick(self) -> None:
            self.refresh()
            self.after(self.poll_ms, self._tick)

    return QueuePanel


try:
    QueuePanel = _build_queue_panel_class()
except Exception:  # pragma: no cover
    QueuePanel = None  # type: ignore
