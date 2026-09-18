# -*- coding: utf-8 -*-
"""История / timeline задач — product cards (FC-03/FC-10)."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import customtkinter as ctk

from ui.paths import agentbus_root
from ui.i18n_ui import t as _t


def _mtime(p: Path) -> float:
    try:
        return p.stat().st_mtime
    except OSError:
        return 0.0


def _read_task(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            data["_path"] = str(path)
            data["_mtime"] = _mtime(path)
            return data
    except Exception:
        pass
    return {"id": path.stem, "message": path.name, "_path": str(path), "_mtime": _mtime(path)}


def collect_history(limit: int = 80) -> list[dict]:
    base = agentbus_root()
    items: list[dict] = []
    root = base / "channels"
    if root.is_dir():
        for state in ("done", "errors", "processing", "deferred", "incoming"):
            for d in root.glob(f"*/{state}"):
                try:
                    for f in d.glob("*.json"):
                        if f.name.endswith(".lease.json"):
                            continue
                        data = _read_task(f)
                        data["_state"] = state
                        data["_channel"] = d.parent.name
                        items.append(data)
                except OSError:
                    continue
    spill = base / ".agentbus" / "desktop_queue"
    if spill.is_dir():
        try:
            for f in spill.glob("*.json"):
                data = _read_task(f)
                data["_state"] = str(data.get("status") or "queued").lower()
                data["_channel"] = "desktop"
                items.append(data)
        except OSError:
            pass
    for state in ("done", "errors", "processing", "deferred"):
        d = base / "channels" / "desktop" / state
        if d.is_dir():
            try:
                for f in d.glob("*.json"):
                    if f.name.endswith(".lease.json"):
                        continue
                    data = _read_task(f)
                    data["_state"] = state
                    data["_channel"] = "desktop"
                    items.append(data)
            except OSError:
                pass
    seen: set[str] = set()
    uniq: list[dict] = []
    for it in items:
        key = f"{it.get('id')}|{it.get('_path')}"
        if key in seen:
            continue
        seen.add(key)
        uniq.append(it)
    uniq.sort(key=lambda x: float(x.get("_mtime") or 0), reverse=True)
    return uniq[:limit]


def _fmt_ts(ts: float) -> str:
    if not ts:
        return "—"
    try:
        return datetime.fromtimestamp(ts).strftime("%m-%d %H:%M:%S")
    except Exception:
        return "—"


def _state_style(state: str) -> tuple[str, str]:
    s = (state or "").lower()
    if s in ("done", "success"):
        return ("✓ done", "#4ec9b0")
    if s in ("errors", "error", "failed"):
        return ("✕ error", "#f14c4c")
    if s in ("processing", "running", "claimed"):
        return ("● run", "#cca700")
    if s in ("deferred",):
        return ("⏳ deferred", "#ce93d8")
    if s in ("queued", "pending", "incoming"):
        return ("○ queue", "#90caf9")
    return (s or "—", "gray")


class HistoryPanel(ctk.CTkFrame):

    def __init__(self, parent, on_resend=None, poll_ms: int = 5000, on_select=None):
        super().__init__(parent)
        self.on_resend = on_resend
        self.on_select = on_select
        self._filter_state = "all"  # all|done|errors|processing
        self._rows_cache: list = []
        self.poll_ms = poll_ms
        self._rows: list[dict] = []

        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=8, pady=4)
        ctk.CTkLabel(
            top,
            text=_t("history_title", default="История задач"),
            font=ctk.CTkFont(size=14, weight="bold"),
        ).pack(side="left")
        ctk.CTkButton(
            top, text=_t("refresh", default="Обновить"), width=90, command=self.refresh
        ).pack(side="right")

        self.scroll = ctk.CTkScrollableFrame(self)
        self.scroll.pack(fill="both", expand=True, padx=8, pady=8)

        try:
            self._build_filters(self)
        except Exception:
            pass
        self.after(400, self.refresh)
        self.after(self.poll_ms, self._tick)


    def _build_filters(self, parent) -> None:
        try:
            bar = ctk.CTkFrame(parent, fg_color="transparent")
            bar.pack(fill="x", padx=6, pady=2)
            for key, label in (
                ("all", "Все"),
                ("done", "Done"),
                ("errors", "Errors"),
                ("processing", "Running"),
                ("deferred", "Deferred"),
            ):
                ctk.CTkButton(
                    bar, text=label, width=64, height=24,
                    command=lambda k=key: self._set_filter(k),
                ).pack(side="left", padx=2)
        except Exception:
            pass

    def _day_label(self, ts: float) -> str:

        try:
            dt = datetime.fromtimestamp(ts)
            today = datetime.now().date()
            d = dt.date()
            if d == today:
                return "Сегодня"
            if (today - d).days == 1:
                return "Вчера"
            return dt.strftime("%d.%m.%Y")
        except Exception:
            return "—"

    def _set_filter(self, state: str) -> None:
        self._filter_state = state or "all"
        self.refresh()

    def refresh(self) -> None:
        def work():
            return collect_history()

        def apply(rows):
            self._rows_cache = list(rows or [])
            st = getattr(self, "_filter_state", "all")
            filtered = list(self._rows_cache)
            if st and st != "all":
                filtered = [
                    r
                    for r in filtered
                    if str(r.get("_state") or "") == st
                    or (st == "errors" and str(r.get("_state")) in ("errors", "error"))
                ]
            for w in self.scroll.winfo_children():
                try:
                    w.destroy()
                except Exception:
                    pass
            self._rows = filtered
            self._last_day_header = None
            if not self._rows:
                try:
                    from app.facade import AppFacade
                    empty = AppFacade().empty_message("history")
                except Exception:
                    empty = _t("history_empty", default="Пока пусто — отправь задачу из чата")
                ctk.CTkLabel(
                    self.scroll,
                    text=empty,
                    text_color="gray",
                ).pack(anchor="w", padx=8, pady=(20, 4))
                ctk.CTkLabel(
                    self.scroll,
                    text=_t(
                        "history_empty_hint",
                        default="Результаты появятся после DONE / ERROR",
                    ),
                    text_color="gray",
                ).pack(anchor="w", padx=8, pady=(0, 20))
                return
            counts: dict[str, int] = {}
            for r in self._rows:
                stt = str(r.get("_state") or "?")
                counts[stt] = counts.get(stt, 0) + 1
            summary = "  ".join(f"{k}:{v}" for k, v in sorted(counts.items()))
            ctk.CTkLabel(
                self.scroll, text=f"Лента · {summary}", text_color="gray"
            ).pack(anchor="w", pady=(0, 6))
            for row in self._rows:
                self._render_row(row)

        try:
            from ui.async_poll import run_bg
            run_bg(self, work, apply, coalesce_key="history")
        except Exception:
            apply(work())

    def _render_row(self, row: dict) -> None:
        try:
            ts = float(row.get("_mtime") or 0)
            day = self._day_label(ts)
            if getattr(self, "_last_day_header", None) != day:
                self._last_day_header = day
                ctk.CTkLabel(
                    self.scroll,
                    text=day,
                    anchor="w",
                    text_color="gray",
                    font=ctk.CTkFont(size=12, weight="bold"),
                ).pack(fill="x", padx=8, pady=(10, 2))
        except Exception:
            pass

        state = str(row.get("_state") or "")
        colors = {
            "done": ("#1b5e20", "#a5d6a7"),
            "errors": ("#b71c1c", "#ef9a9a"),
            "error": ("#b71c1c", "#ef9a9a"),
            "processing": ("#e65100", "#ffe0b2"),
            "incoming": ("#1565c0", "#90caf9"),
            "queued": ("#1565c0", "#90caf9"),
            "pending": ("#1565c0", "#90caf9"),
            "deferred": ("#4a148c", "#ce93d8"),
        }
        fg = colors.get(state, ("gray30", "gray70"))
        frame = ctk.CTkFrame(self.scroll)
        frame.pack(fill="x", pady=3)
        tid_full = str(row.get("id") or Path(str(row.get("_path", ""))).stem)

        def _open_row(_e=None, _tid=tid_full, _row=row):
            try:
                if getattr(self, "on_select", None):
                    self.on_select(str(_tid), _row)
                else:
                    self._show_details(_row)
            except Exception:
                try:
                    self._show_details(_row)
                except Exception:
                    pass

        try:
            frame.bind("<Button-1>", _open_row)
            frame.bind("<Double-Button-1>", _open_row)
        except Exception:
            pass

        head = ctk.CTkFrame(frame, fg_color="transparent")
        head.pack(fill="x", padx=6, pady=(4, 0))
        tid = str(row.get("id") or Path(str(row.get("_path", ""))).stem)[:18]
        label, _col = _state_style(state)
        ctk.CTkLabel(
            head, text=f"{label}  {tid}",
            text_color=fg[1] if isinstance(fg, tuple) else fg,
        ).pack(side="left")
        ctk.CTkLabel(
            head, text=_fmt_ts(float(row.get("_mtime") or 0)), text_color="gray"
        ).pack(side="right")

        proj = str(row.get("project") or "")
        ch = str(row.get("_channel") or "")
        ch_disp = "чат ПК" if ch == "desktop" else ch
        ctk.CTkLabel(
            frame, text=f"{proj or '—'} · {ch_disp}", text_color="gray", anchor="w"
        ).pack(fill="x", padx=8)

        # FC-10 product card
        try:
            from core.task_result import history_card_lines
            card = history_card_lines(row)
        except Exception:
            card = {"prompt": str(row.get("message") or "")[:160], "meta": "", "verify": "", "files": "", "error": "", "lifecycle": "", "summary": ""}

        prompt = card.get("prompt") or str(row.get("message") or "")[:160].replace("\n", " ")
        ctk.CTkLabel(
            frame,
            text=prompt or _t("history_no_message", default="(без текста)"),
            anchor="w",
            justify="left",
        ).pack(fill="x", padx=8, pady=(0, 2))

        if card.get("meta"):
            ctk.CTkLabel(frame, text=card["meta"], text_color="gray60", anchor="w").pack(
                fill="x", padx=8
            )
        if card.get("lifecycle"):
            ctk.CTkLabel(
                frame, text=card["lifecycle"], text_color="gray",
                anchor="w", font=ctk.CTkFont(size=10),
            ).pack(fill="x", padx=8)
        if card.get("retry"):
            ctk.CTkLabel(
                frame, text=card["retry"], text_color="#ce93d8",
                anchor="w", font=ctk.CTkFont(size=11),
            ).pack(fill="x", padx=8)
        if card.get("trace"):
            ctk.CTkLabel(
                frame, text=card["trace"], text_color="gray50",
                anchor="w", font=ctk.CTkFont(size=10),
            ).pack(fill="x", padx=8)
        verify_line = card.get("verify") or ""
        if verify_line:
            ok_v = "PASS" in verify_line and "FAIL" not in verify_line
            ctk.CTkLabel(
                frame, text=verify_line, anchor="w",
                text_color=("#4ec9b0" if ok_v else "#f14c4c" if "FAIL" in verify_line else "gray"),
            ).pack(fill="x", padx=8)
        if card.get("files"):
            ctk.CTkLabel(frame, text=card["files"], text_color="gray", anchor="w").pack(
                fill="x", padx=8
            )
        if card.get("error") and state in ("errors", "error"):
            ctk.CTkLabel(
                frame, text=f"Ошибка: {card['error']}", anchor="w",
                text_color="#f14c4c",
            ).pack(fill="x", padx=8)
        elif state in ("done", "errors", "deferred") and not verify_line and not card.get("meta"):
            try:
                from ui.result_text import extract_result_text
                out = extract_result_text(row)[:220]
            except Exception:
                out = ""
            if out and out not in (prompt, "готово"):
                ctk.CTkLabel(
                    frame, text=out, anchor="w", justify="left",
                    text_color=("#4ec9b0" if state == "done" else "#f14c4c" if state.startswith("err") else "gray"),
                ).pack(fill="x", padx=8, pady=(0, 2))

        btns = ctk.CTkFrame(frame, fg_color="transparent")
        btns.pack(fill="x", padx=6, pady=(0, 4))
        if self.on_resend and state in ("done", "errors", "error", "deferred"):
            ctk.CTkButton(
                btns, text=_t("resend", default="↻ снова"), width=70, height=24,
                command=lambda r=row: self._resend(r),
            ).pack(side="left", padx=2)
        ctk.CTkButton(
            btns, text=_t("details", default="детали"), width=70, height=24,
            command=lambda r=row: self._show_details(r),
        ).pack(side="left", padx=2)

    def _resend(self, row: dict) -> None:
        if self.on_resend:
            self.on_resend(row)

    def _show_details(self, row: dict) -> None:
        win = ctk.CTkToplevel(self)
        win.title(str(row.get("id") or "task"))
        win.geometry("640x520")
        human = ""
        try:
            from core.task_result import history_detail_text
            human = history_detail_text(row)
        except Exception:
            try:
                from core.task_result import build_task_result
                human = build_task_result(row).format_human()
            except Exception:
                try:
                    from ui.result_text import extract_result_text
                    human = extract_result_text(row)
                except Exception:
                    human = ""
        if human:
            ctk.CTkLabel(
                win, text=human[:1600], anchor="w", justify="left", wraplength=600,
            ).pack(fill="x", padx=10, pady=(8, 4))
        ctk.CTkLabel(win, text="JSON", text_color="gray", anchor="w").pack(fill="x", padx=10)
        box = ctk.CTkTextbox(win)
        box.pack(fill="both", expand=True, padx=8, pady=8)
        try:
            text = json.dumps(row, ensure_ascii=False, indent=2, default=str)
        except Exception:
            text = str(row)
        box.insert("1.0", text)
        box.configure(state="disabled")

    def _tick(self) -> None:
        self.refresh()
        self.after(self.poll_ms, self._tick)
