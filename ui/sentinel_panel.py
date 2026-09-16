# -*- coding: utf-8 -*-
"""File Sentinel UI — quarantine list + shadow _v2 Merge / Discard."""
from __future__ import annotations

from pathlib import Path

import customtkinter as ctk

from ui.paths import agentbus_root, ensure_sys_path
from ui.i18n_ui import t as _t


class SentinelPanel(ctk.CTkFrame):
    def __init__(self, parent, get_project=None, poll_ms: int = 6000):
        super().__init__(parent)
        self.poll_ms = poll_ms
        self.get_project = get_project  # callable → project path or None
        self._shadow_frames: list[ctk.CTkFrame] = []

        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=8, pady=4)
        ctk.CTkLabel(
            top,
            text=_t("sentinel_title", default="Sentinel"),
            font=ctk.CTkFont(size=14, weight="bold"),
        ).pack(side="left")
        ctk.CTkButton(
            top, text=_t("refresh", default="Обновить"), width=90, command=self.refresh
        ).pack(side="right", padx=2)
        ctk.CTkButton(
            top, text="Scan junk", width=90, command=self._scan_junk
        ).pack(side="right", padx=2)

        self.status = ctk.CTkLabel(self, text="", anchor="w", text_color="gray")
        self.status.pack(fill="x", padx=10)

        # Shadows
        ctk.CTkLabel(
            self, text="Shadow candidates (*_v2 / _new)", anchor="w",
            font=ctk.CTkFont(weight="bold"),
        ).pack(fill="x", padx=10, pady=(8, 2))
        self.shadow_scroll = ctk.CTkScrollableFrame(self, height=180)
        self.shadow_scroll.pack(fill="both", expand=True, padx=8, pady=4)

        # Quarantine
        ctk.CTkLabel(
            self, text="Quarantine (.agentbus/quarantine)", anchor="w",
            font=ctk.CTkFont(weight="bold"),
        ).pack(fill="x", padx=10, pady=(8, 2))
        self.q_box = ctk.CTkTextbox(
            self, height=120, font=ctk.CTkFont(family="Consolas", size=11)
        )
        self.q_box.pack(fill="x", padx=8, pady=4)

        self.after(700, self.refresh)
        self.after(self.poll_ms, self._tick)

    def _tick(self) -> None:
        try:
            self.refresh()
        finally:
            self.after(self.poll_ms, self._tick)

    def _project_root(self) -> Path:
        if callable(self.get_project):
            try:
                p = self.get_project()
                if p:
                    return Path(p)
            except Exception:
                pass
        return agentbus_root()

    def _sentinel(self):
        ensure_sys_path()
        from file_sentinel import FileSentinel
        return FileSentinel(self._project_root())

    def refresh(self) -> None:
        for fr in self._shadow_frames:
            try:
                fr.destroy()
            except Exception:
                pass
        self._shadow_frames.clear()

        try:
            sent = self._sentinel()
            shadows = sent.find_shadows()
        except Exception as exc:
            self.status.configure(text=f"sentinel error: {exc}")
            shadows = []

        if not shadows:
            empty = ctk.CTkLabel(
                self.shadow_scroll, text="(нет shadow-файлов)", text_color="gray"
            )
            empty.pack(anchor="w", padx=4, pady=4)
            self._shadow_frames.append(empty)  # type: ignore
        else:
            for sh in shadows:
                self._add_shadow_card(sh)

        # quarantine listing
        self.q_box.configure(state="normal")
        self.q_box.delete("1.0", "end")
        qroot = self._project_root() / ".agentbus" / "quarantine"
        lines = []
        if qroot.is_dir():
            entries = sorted(qroot.rglob("*"), key=lambda p: p.stat().st_mtime, reverse=True)
            files = [p for p in entries if p.is_file()][:40]
            for p in files:
                try:
                    rel = p.relative_to(qroot)
                except ValueError:
                    rel = p
                lines.append(str(rel))
        if not lines:
            lines = ["(пусто)"]
        self.q_box.insert("1.0", "\n".join(lines))
        self.q_box.configure(state="disabled")
        self.status.configure(
            text=f"project={self._project_root().name}  shadows={len(shadows)}  q={len(lines) if lines != ['(пусто)'] else 0}"
        )

    def _add_shadow_card(self, sh) -> None:
        fr = ctk.CTkFrame(self.shadow_scroll, corner_radius=6)
        fr.pack(fill="x", pady=3, padx=2)
        self._shadow_frames.append(fr)

        data = sh.to_dict() if hasattr(sh, "to_dict") else dict(sh)
        shadow = data.get("shadow", "")
        target = data.get("target", "")
        ok = bool(data.get("syntax_ok", False))
        badge = "OK" if ok else "SYNTAX"
        color = "#27ae60" if ok else "#c0392b"
        head = ctk.CTkFrame(fr, fg_color="transparent")
        head.pack(fill="x", padx=6, pady=4)
        ctk.CTkLabel(
            head, text=f" {badge} ", fg_color=color, text_color="#fff",
            corner_radius=4, font=ctk.CTkFont(size=10, weight="bold"),
        ).pack(side="left", padx=2)
        ctk.CTkLabel(
            head, text=f"{shadow}  →  {target}", anchor="w"
        ).pack(side="left", padx=6)

        btns = ctk.CTkFrame(fr, fg_color="transparent")
        btns.pack(fill="x", padx=6, pady=4)
        ctk.CTkButton(
            btns, text="Merge", width=80, fg_color="#1e8449",
            command=lambda s=shadow: self._merge(s),
            state="normal" if ok else "disabled",
        ).pack(side="left", padx=3)
        ctk.CTkButton(
            btns, text="Discard", width=80, fg_color="#922b21",
            command=lambda s=shadow: self._discard(s),
        ).pack(side="left", padx=3)
        notes = data.get("notes") or ""
        if notes:
            ctk.CTkLabel(
                fr, text=notes[:120], text_color="gray",
                font=ctk.CTkFont(size=10),
            ).pack(anchor="w", padx=10, pady=(0, 4))

    def _merge(self, shadow_rel: str) -> None:
        try:
            res = self._sentinel().promote_shadow(shadow_rel, dry_run=False)
            self.status.configure(text=f"merge: {res}")
        except Exception as exc:
            self.status.configure(text=f"merge error: {exc}")
        self.refresh()

    def _discard(self, shadow_rel: str) -> None:
        try:
            sent = self._sentinel()
            p = sent.root / shadow_rel
            action = sent.quarantine(p, reason="shadow_discard")
            self.status.configure(text=f"discard: {action}")
        except Exception as exc:
            self.status.configure(text=f"discard error: {exc}")
        self.refresh()

    def _scan_junk(self) -> None:
        try:
            report = self._sentinel().scan_and_quarantine_junk()
            self.status.configure(
                text=f"junk quarantined={len(report.quarantined)} protected={len(report.protected)}"
            )
        except Exception as exc:
            self.status.configure(text=f"scan error: {exc}")
        self.refresh()
