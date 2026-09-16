# -*- coding: utf-8 -*-
"""PEV Plan Inspector — view/edit .agentbus/current_plan.md + progress marks."""
from __future__ import annotations

import json
import re
from pathlib import Path

import customtkinter as ctk

from ui.paths import agentbus_root
from ui.i18n_ui import t as _t


class PevPanel(ctk.CTkFrame):
    """Show current Plan-Execute-Verify plan; allow save back to disk."""

    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        self._project: Path | None = None

        head = ctk.CTkFrame(self)
        head.pack(fill="x", padx=8, pady=6)
        ctk.CTkLabel(head, text=_t("pev_title", default="PEV Plan"), font=ctk.CTkFont(weight="bold")).pack(
            side="left"
        )
        ctk.CTkButton(head, text=_t("refresh", default="Обновить"), width=90, command=self.reload).pack(
            side="right", padx=4
        )
        ctk.CTkButton(head, text=_t("save", default="Сохранить"), width=90, command=self.save).pack(
            side="right", padx=4
        )

        self.path_lbl = ctk.CTkLabel(self, text="", anchor="w", text_color="gray")
        self.path_lbl.pack(fill="x", padx=10)

        self.box = ctk.CTkTextbox(self, wrap="word")
        self.box.pack(fill="both", expand=True, padx=8, pady=8)

        self.status = ctk.CTkLabel(self, text="", anchor="w")
        self.status.pack(fill="x", padx=10, pady=(0, 6))

        self.reload()

    def set_project(self, path: str | Path | None) -> None:
        self._project = Path(path) if path else None
        self.reload()

    def _plan_path(self) -> Path | None:
        roots = []
        if self._project:
            roots.append(self._project)
        roots.append(agentbus_root())
        for r in roots:
            p = Path(r) / ".agentbus" / "current_plan.md"
            if p.is_file():
                return p
        base = self._project or agentbus_root()
        return Path(base) / ".agentbus" / "current_plan.md"

    def _progress_path(self) -> Path:
        base = self._project or agentbus_root()
        return Path(base) / ".agentbus" / "pev_progress.json"

    def _annotate_plan(self, text: str) -> str:
        """Mark completed steps using pev_progress.json (done_steps: 1-based)."""
        done: set[int] = set()
        st = ""
        prog = self._progress_path()
        if prog.is_file():
            try:
                data = json.loads(prog.read_text(encoding="utf-8"))
                done = {int(x) for x in (data.get("done_steps") or [])}
                st = str(data.get("status") or "")
            except Exception:
                pass
        lines = []
        for ln in (text or "").splitlines():
            m = re.match(r"^(\s*)(\d+)\.(\s+)(.*)$", ln)
            if m and int(m.group(2)) in done:
                lines.append(f"{m.group(1)}{m.group(2)}.[x] {m.group(4)}")
            else:
                lines.append(ln)
        if st:
            lines.append("")
            lines.append(f"<!-- pev status: {st} -->")
        return "\n".join(lines)

    def reload(self) -> None:
        path = self._plan_path()
        self.box.delete("1.0", "end")
        if path is None:
            self.path_lbl.configure(text="(no project)")
            return
        self.path_lbl.configure(text=str(path))
        if path.is_file():
            try:
                raw = path.read_text(encoding="utf-8", errors="replace")
                self.box.insert("1.0", self._annotate_plan(raw))
                self.status.configure(text=_t("pev_loaded", default="План загружен"))
            except OSError as exc:
                self.status.configure(text=f"read error: {exc}")
        else:
            self.box.insert(
                "1.0",
                "# No plan yet\n\nRun a task with complexity >= PEV min to generate current_plan.md\n",
            )
            self.status.configure(text=_t("pev_empty", default="Плана нет"))

    def save(self) -> None:
        path = self._plan_path()
        if path is None:
            return
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(self.box.get("1.0", "end").rstrip() + "\n", encoding="utf-8")
            self.status.configure(text=_t("pev_saved", default="Сохранено"))
        except OSError as exc:
            self.status.configure(text=f"save error: {exc}")
