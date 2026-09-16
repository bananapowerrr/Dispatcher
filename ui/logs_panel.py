# -*- coding: utf-8 -*-
"""Logs: хвост логов + детект DONE/ERROR для UI."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Callable

import customtkinter as ctk

from ui.paths import agentbus_root
from ui.i18n_ui import t as _t


class LogsPanel(ctk.CTkFrame):
    def __init__(
        self,
        parent,
        poll_ms: int = 1200,
        on_done: Callable[[str, str], None] | None = None,
        on_error: Callable[[str, str], None] | None = None,
    ):
        super().__init__(parent)
        self.poll_ms = poll_ms
        self.on_done = on_done
        self.on_error = on_error
        self._offsets: dict[Path, int] = {}
        self._seen_done: set[str] = set()

        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=8, pady=4)
        ctk.CTkLabel(top, text=_t("logs_title", default="Логи"), font=ctk.CTkFont(size=14, weight="bold")).pack(side="left")
        ctk.CTkButton(top, text=_t("clear", default="Очистить"), width=90, command=self.clear).pack(side="right", padx=4)
        ctk.CTkButton(top, text=_t("export", default="Экспорт"), width=90, command=self.export_log).pack(side="right", padx=4)

        self.box = ctk.CTkTextbox(self, state="disabled", wrap="word")
        self.box.pack(fill="both", expand=True, padx=8, pady=8)

        self.queue_lbl = ctk.CTkLabel(self, text=_t("queue_label", default="Очередь: —"), anchor="w", text_color="gray")
        self.queue_lbl.pack(fill="x", padx=10, pady=(0, 8))

        self.after(self.poll_ms, self._tick)

    def export_log(self) -> None:
        """Сохранить видимый лог в .agentbus/exports/."""
        try:
            root = agentbus_root()
            out_dir = root / ".agentbus" / "exports"
            out_dir.mkdir(parents=True, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            path = out_dir / f"session_log_{ts}.txt"
            text = self.box.get("1.0", "end")
            path.write_text(text, encoding="utf-8")
            self._append(f"[export] {path}")
        except Exception as exp:
            self._append(f"[export error] {exp}")

    def clear(self) -> None:
        self.box.configure(state="normal")
        self.box.delete("1.0", "end")
        self.box.configure(state="disabled")

    def _append(self, line: str) -> None:
        self.box.configure(state="normal")
        try:
            self.box.tag_config("ok", foreground="#4ec9b0")
            self.box.tag_config("err", foreground="#f14c4c")
            self.box.tag_config("warn", foreground="#cca700")
            self.box.tag_config("dim", foreground="#858585")
        except Exception:
            pass
        low = (line or "").lower()
        tag = None
        if "error" in low or "failed" in low or "traceback" in low:
            tag = "err"
        elif "done" in low or "success" in low:
            tag = "ok"
        elif "warn" in low or "cooldown" in low:
            tag = "warn"
        elif "claim" in low or "phase" in low:
            tag = "dim"
        text = line.rstrip() + "\n"
        if tag:
            self.box.insert("end", text, tag)
        else:
            self.box.insert("end", text)
        self.box.see("end")
        self.box.configure(state="disabled")

    def _candidate_files(self) -> list[Path]:
        root = agentbus_root()
        out: list[Path] = []
        for p in (
            root / "eventbus.jsonl",
            root / ".agentbus" / "events.jsonl",
            root / "logs" / "events.jsonl",
        ):
            if p.is_file():
                out.append(p)
        ch = root / "channels"
        if ch.is_dir():
            for logdir in ch.glob("*/logs"):
                for f in sorted(logdir.glob("*.log"))[-8:]:
                    out.append(f)
                for f in sorted(logdir.glob("*.jsonl"))[-8:]:
                    out.append(f)
        return out

    def _emit_terminal(self, line: str) -> None:
        low = line.lower()
        # file names in done/ often appear in logs
        if " done" in f" {low}" or low.startswith("done") or '"status": "done"' in low:
            key = line[:120]
            if key not in self._seen_done:
                self._seen_done.add(key)
                if self.on_done:
                    self.on_done("", line[:200])
        if " error" in f" {low}" or low.startswith("error") or '"status": "error"' in low:
            if self.on_error:
                self.on_error("", line[:200])


    def _enrich_detail(self, task_id: str, fallback: str) -> str:
        """Prefer human summary from done/errors JSON when task_id known."""
        tid = (task_id or "").strip()
        if not tid:
            return fallback
        try:
            from ui.result_text import extract_result_text
            root = agentbus_root() / "channels"
            for state in ("done", "errors"):
                for d in root.glob(f"*/{state}"):
                    f = d / f"{tid}.json"
                    if not f.is_file():
                        # also match stem contains id
                        for cand in d.glob(f"*{tid}*.json"):
                            f = cand
                            break
                    if f.is_file():
                        import json as _json
                        data = _json.loads(f.read_text(encoding="utf-8"))
                        if isinstance(data, dict):
                            s = extract_result_text(data)
                            if s:
                                return s[:400]
        except Exception:
            pass
        return fallback

    def _read_new(self, path: Path) -> None:
        try:
            data = path.read_bytes()
        except OSError:
            return
        off = self._offsets.get(path, 0)
        if off > len(data):
            off = 0
        chunk = data[off:]
        if not chunk:
            return
        self._offsets[path] = len(data)
        text = chunk.decode("utf-8", errors="replace")
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            if line.startswith("{"):
                try:
                    obj = json.loads(line)
                    msg = obj.get("message") or obj.get("type") or line[:200]
                    typ = str(obj.get("type", "LOG")).upper()
                    self._append(f"{typ}: {msg}")
                    if typ in {"DONE", "TASK_DONE"} or str(obj.get("status", "")).upper() == "DONE":
                        tid = str(obj.get("task_id") or obj.get("id") or "")
                        if tid not in self._seen_done:
                            self._seen_done.add(tid or msg[:80])
                            if self.on_done:
                                self.on_done(tid, self._enrich_detail(tid, str(msg)[:200]))
                    if typ in {"ERROR", "TASK_ERROR"} or str(obj.get("status", "")).upper() == "ERROR":
                        if self.on_error:
                            self.on_error(str(obj.get("task_id") or ""), self._enrich_detail(str(obj.get("task_id") or ""), str(msg)[:200]))
                    continue
                except Exception:
                    pass
            self._append(line[:500])
            self._emit_terminal(line)

    def _update_queue(self) -> None:
        root = agentbus_root() / "channels"
        counts = {"incoming": 0, "processing": 0, "done": 0, "errors": 0, "deferred": 0}
        if root.is_dir():
            for state in counts:
                for d in root.glob(f"*/{state}"):
                    try:
                        counts[state] += sum(1 for p in d.iterdir() if p.is_file() and p.suffix == ".json")
                    except OSError:
                        pass
        desk_q = 0
        try:
            spill = agentbus_root() / ".agentbus" / "desktop_queue"
            if spill.is_dir():
                desk_q = sum(1 for p in spill.glob("*.json") if p.is_file())
        except OSError:
            pass
        self.queue_lbl.configure(
            text=(
                f"Очередь  chat:{desk_q}  in:{counts['incoming']}  run:{counts['processing']}  "
                f"done:{counts['done']}  err:{counts['errors']}  def:{counts['deferred']}"
            )
        )

    def _tick(self) -> None:
        def work():
            # return queue counts only; log tails still short reads on apply path
            root = agentbus_root() / "channels"
            counts = {"incoming": 0, "processing": 0, "done": 0, "errors": 0, "deferred": 0, "desktop": 0}
            if root.is_dir():
                for state in list(counts.keys()):
                    if state == "desktop":
                        continue
                    for d in root.glob(f"*/{state}"):
                        try:
                            counts[state] += sum(
                                1 for p in d.iterdir() if p.is_file() and p.suffix == ".json"
                            )
                        except OSError:
                            pass
            try:
                spill = agentbus_root() / ".agentbus" / "desktop_queue"
                if spill.is_dir():
                    counts["desktop"] = sum(1 for p in spill.glob("*.json") if p.is_file())
            except OSError:
                pass
            return counts

        def apply(counts):
            for f in self._candidate_files():
                self._read_new(f)
            if counts:
                self.queue_lbl.configure(
                    text=(
                        f"Очередь  chat:{counts.get('desktop', 0)}  in:{counts['incoming']}  "
                        f"run:{counts['processing']}  done:{counts['done']}  "
                        f"err:{counts['errors']}  def:{counts['deferred']}"
                    )
                )

        try:
            from ui.async_poll import run_bg
            run_bg(self, work, apply, coalesce_key="logs")
        except Exception:
            for f in self._candidate_files():
                self._read_new(f)
            self._update_queue()
        self.after(self.poll_ms, self._tick)
