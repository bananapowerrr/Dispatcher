# -*- coding: utf-8 -*-
"""Live Worker Dashboard — health badges + last TaskResult outcome (FC-08)."""
from __future__ import annotations

import json
from pathlib import Path

import customtkinter as ctk

from ui.paths import agentbus_root, ensure_sys_path
from ui.i18n_ui import t as _t


STATUS_LABEL_RU = {
    "HEALTHY": "OK",
    "BUSY": "занят",
    "COOLDOWN": "пауза",
    "RATE_LIMIT": "лимит",
    "CIRCUIT": "отключён",
    "DEGRADED": "слабо",
    "BILLING": "биллинг",
    "UNAVAILABLE": "нет",
    "UNKNOWN": "?",
    "AVAILABLE": "OK",
}

STATUS_COLOR = {
    "HEALTHY": "#27ae60",
    "BUSY": "#2980b9",
    "COOLDOWN": "#f39c12",
    "RATE_LIMIT": "#e67e22",
    "CIRCUIT": "#c0392b",
    "DEGRADED": "#8e44ad",
    "BILLING": "#922b21",
    "UNAVAILABLE": "#7f8c8d",
    "UNKNOWN": "#95a5a6",
    "AVAILABLE": "#27ae60",
}


def _workers_state_path() -> Path | None:
    root = agentbus_root()
    for p in (
        root / ".agentbus" / "workers_state.json",
        root / "workers_state.json",
        root / "config" / "workers_state.json",
    ):
        if p.is_file():
            return p
    return root / ".agentbus" / "workers_state.json"


def _load_rows() -> list[dict]:
    ensure_sys_path()
    try:
        from safety.health import HealthRegistry
        reg = HealthRegistry()
        return reg.dashboard_rows()
    except Exception:
        pass
    path = _workers_state_path()
    if not path or not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    rows = []
    for name, raw in sorted((data or {}).items()):
        if not isinstance(raw, dict):
            continue
        st = str(raw.get("status") or "UNKNOWN")
        if st in ("AVAILABLE", ""):
            st = "HEALTHY"
        rows.append({
            "worker": name,
            "status": st,
            "running": int(raw.get("running_count") or 0),
            "success_rate": float(raw.get("success_rate") or 0),
            "latency_avg": float(raw.get("latency_avg") or 0),
            "tasks_completed": int(raw.get("tasks_completed") or 0),
            "cooldown_sec": 0,
            "last_error": str(raw.get("last_error") or "")[:80],
            "score": -1,
        })
    return rows


def _load_last_by_worker() -> dict[str, dict]:
    try:
        ensure_sys_path()
        from ui.last_outcome import last_outcomes_by_worker
        return last_outcomes_by_worker(agentbus_root(), limit=40)
    except Exception:
        return {}


class WorkersPanel(ctk.CTkFrame):
    def __init__(self, parent, poll_ms: int = 3000):
        super().__init__(parent)
        self.poll_ms = poll_ms
        self._row_frames: list[ctk.CTkFrame] = []

        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=8, pady=4)
        ctk.CTkLabel(
            top,
            text=_t("workers_title", default="Воркеры"),
            font=ctk.CTkFont(size=14, weight="bold"),
        ).pack(side="left")
        ctk.CTkButton(
            top, text=_t("refresh", default="Обновить"), width=90, command=self.refresh
        ).pack(side="right")

        leg = ctk.CTkFrame(self, fg_color="transparent")
        leg.pack(fill="x", padx=8, pady=(0, 4))
        for key, label in (
            ("HEALTHY", "OK"),
            ("BUSY", "занят"),
            ("COOLDOWN", "пауза"),
            ("CIRCUIT", "отключён"),
            ("DEGRADED", "слабо"),
        ):
            color = STATUS_COLOR[key]
            badge = ctk.CTkLabel(
                leg, text=f" {label} ", fg_color=color, corner_radius=4,
                text_color="#ffffff", font=ctk.CTkFont(size=10, weight="bold"),
            )
            badge.pack(side="left", padx=3)

        self.scroll = ctk.CTkScrollableFrame(self)
        self.scroll.pack(fill="both", expand=True, padx=8, pady=8)

        self.empty_lbl = ctk.CTkLabel(
            self.scroll,
            text=_t("workers_empty", default="Нет данных — запустите диспетчер слева"),
            text_color="gray",
        )
        self.empty_lbl.pack(anchor="w", padx=4, pady=8)

        self.after(400, self.refresh)
        self.after(self.poll_ms, self._tick)

    def _tick(self) -> None:
        try:
            self.refresh()
        finally:
            self.after(self.poll_ms, self._tick)

    def _clear_rows(self) -> None:
        for fr in self._row_frames:
            try:
                fr.destroy()
            except Exception:
                pass
        self._row_frames.clear()
        try:
            self.empty_lbl.pack_forget()
        except Exception:
            pass

    def refresh(self) -> None:
        def work():
            return _load_rows(), _load_last_by_worker()

        def apply(payload):
            rows, last_map = payload if isinstance(payload, tuple) else (payload, {})
            self._clear_rows()
            if not rows and not last_map:
                self.empty_lbl.pack(anchor="w", padx=4, pady=8)
                return
            if not rows and last_map:
                for name, tr in sorted(last_map.items()):
                    self._add_row({
                        "worker": name, "status": "UNKNOWN", "running": 0,
                        "success_rate": 0, "latency_avg": 0, "tasks_completed": 0,
                        "cooldown_sec": 0, "last_error": "", "score": -1,
                    }, tr)
                return
            for r in rows:
                name = str(r.get("worker") or "")
                tr = last_map.get(name) or last_map.get(name.lower())
                if tr is None:
                    for k, v in last_map.items():
                        if name and (name in k or k in name):
                            tr = v
                            break
                self._add_row(r, tr)

        try:
            from ui.async_poll import run_bg
            run_bg(self, work, apply, coalesce_key="workers")
        except Exception:
            apply(work())

    def _add_row(self, r: dict, last: dict | None = None) -> None:
        fr = ctk.CTkFrame(self.scroll, corner_radius=6)
        fr.pack(fill="x", pady=3, padx=2)
        self._row_frames.append(fr)

        st = str(r.get("status") or "UNKNOWN")
        color = STATUS_COLOR.get(st, STATUS_COLOR["UNKNOWN"])
        badge = ctk.CTkLabel(
            fr, text=f" {STATUS_LABEL_RU.get(st, st)} ",
            fg_color=color, text_color="#ffffff", corner_radius=4,
            font=ctk.CTkFont(size=11, weight="bold"), width=100,
        )
        badge.pack(side="left", padx=6, pady=6)

        name = str(r.get("worker") or "")
        info = (
            f"{name}   в работе={int(r.get('running') or 0)}  "
            f"успех={float(r.get('success_rate') or 0)*100:.0f}%  "
            f"задержка={float(r.get('latency_avg') or 0):.1f}с  "
            f"готово={int(r.get('tasks_completed') or 0)}"
        )
        mid = ctk.CTkFrame(fr, fg_color="transparent")
        mid.pack(side="left", fill="x", expand=True, padx=4)
        ctk.CTkLabel(mid, text=info, anchor="w").pack(fill="x")

        if last:
            try:
                from ui.last_outcome import format_worker_line
                line = format_worker_line(last)
            except Exception:
                line = str(last.get("status") or "")
            if line:
                ctk.CTkLabel(
                    mid, text=f"последняя: {line}", anchor="w",
                    text_color="gray", font=ctk.CTkFont(size=10),
                ).pack(fill="x")
            ch = last.get("changes") if isinstance(last.get("changes"), dict) else {}
            files = ch.get("files") if isinstance(ch, dict) else None
            if files:
                n = len(files)
                ins = int(ch.get("insertions") or 0)
                de = int(ch.get("deletions") or 0)
                extra = f" +{ins} -{de}" if (ins or de) else ""
                ctk.CTkLabel(
                    mid,
                    text=f"файлы: {n}{extra} · " + ", ".join(str(x) for x in files[:3]),
                    anchor="w", text_color="gray", font=ctk.CTkFont(size=10),
                ).pack(fill="x")
            err = str(last.get("error") or "").strip()
            if err and not last.get("ok"):
                ctk.CTkLabel(
                    mid, text=f"ошибка: {err[:80]}", anchor="w",
                    text_color="#f14c4c", font=ctk.CTkFont(size=10),
                ).pack(fill="x")

        extra = []
        cd = int(r.get("cooldown_sec") or 0)
        if cd > 0:
            extra.append(f"cd {cd}s")
        err = str(r.get("last_error") or "").strip()
        if err:
            extra.append(err[:60])
        if extra:
            ctk.CTkLabel(
                fr, text=" · ".join(extra), text_color="gray",
                font=ctk.CTkFont(size=10),
            ).pack(side="right", padx=8)
