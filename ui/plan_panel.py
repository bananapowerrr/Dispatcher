# -*- coding: utf-8 -*-
"""P2 Plan panel — LivingPlan via PlanService (not a second planner)."""
from __future__ import annotations

from typing import Any, Callable

try:
    import customtkinter as ctk
except ImportError:  # pragma: no cover
    ctk = None  # type: ignore


class PlanPanel(ctk.CTkFrame if ctk else object):  # type: ignore
    def __init__(
        self,
        master,
        *,
        get_project: Callable[[], str] | None = None,
        **kwargs: Any,
    ):
        if ctk is None:
            raise RuntimeError("customtkinter required")
        super().__init__(master, **kwargs)
        self._get_project = get_project or (lambda: "")
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=8, pady=4)
        ctk.CTkLabel(top, text="Plan", font=ctk.CTkFont(size=14, weight="bold")).pack(side="left")
        ctk.CTkButton(top, text="↻", width=36, command=self.refresh).pack(side="right")
        ctk.CTkButton(top, text="↑", width=32, command=lambda: self._move(-1)).pack(side="right", padx=2)
        ctk.CTkButton(top, text="↓", width=32, command=lambda: self._move(1)).pack(side="right", padx=2)
        ctk.CTkButton(top, text="Cancel", width=70, command=self._cancel).pack(side="right", padx=2)
        self._list = ctk.CTkTextbox(self, height=180, font=ctk.CTkFont(family="Consolas", size=12))
        self._list.pack(fill="both", expand=True, padx=8, pady=4)
        self._status = ctk.CTkLabel(self, text="", anchor="w", text_color="gray")
        self._status.pack(fill="x", padx=8, pady=2)
        self._selected = ""
        self.after(400, self.refresh)

    def _root(self) -> str:
        try:
            r = self._get_project()
            return (r() if callable(r) else r) or ""
        except Exception:
            return ""

    def refresh(self) -> None:
        root = self._root()
        self._list.delete("1.0", "end")
        if not root:
            self._list.insert("1.0", "(нет проекта)")
            return
        try:
            from app.plan_service import PlanService
            data = PlanService(root).list_plan()
            lines = [f"v{data.get('version')}  {data.get('summary') or ''}", ""]
            for s in data.get("steps") or []:
                lines.append(
                    f"[{s.get('status')}] {s.get('id')}: {s.get('action')}"
                )
            self._list.insert("1.0", "\n".join(lines) or "(пустой план)")
            self._status.configure(
                text=f"active={data.get('active')} finished={data.get('finished')}"
            )
        except Exception as e:
            self._list.insert("1.0", str(e))

    def _selected_id(self) -> str:
        try:
            line = self._list.get("insert linestart", "insert lineend").strip()
            if line.startswith("[") and "]" in line:
                rest = line.split("]", 1)[1].strip()
                return rest.split(":", 1)[0].strip()
        except Exception:
            pass
        return self._selected

    def _move(self, delta: int) -> None:
        sid = self._selected_id()
        root = self._root()
        if not sid or not root:
            return
        try:
            from app.plan_service import PlanService
            r = PlanService(root).move_step(sid, delta=delta)
            if r.get("warning"):
                self._status.configure(text=r["warning"])
            self.refresh()
        except Exception as e:
            self._status.configure(text=str(e)[:120])

    def _cancel(self) -> None:
        sid = self._selected_id()
        root = self._root()
        if not sid or not root:
            return
        try:
            from app.plan_service import PlanService
            ok = PlanService(root).cancel_step(sid, reason="cancelled from Plan UI")
            self._status.configure(text="cancelled" if ok else "cannot cancel")
            self.refresh()
        except Exception as e:
            self._status.configure(text=str(e)[:120])
