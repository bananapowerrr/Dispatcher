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
        ctk.CTkButton(top, text="В очередь", width=90, command=self._enqueue_selected).pack(side="right", padx=2)
        ctk.CTkButton(top, text="DONE", width=56, command=self._mark_done).pack(side="right", padx=2)
        ctk.CTkButton(top, text="↑", width=32, command=lambda: self._move(-1)).pack(side="right", padx=2)
        ctk.CTkButton(top, text="↓", width=32, command=lambda: self._move(1)).pack(side="right", padx=2)
        ctk.CTkButton(top, text="Cancel", width=70, command=self._cancel).pack(side="right", padx=2)
        ctk.CTkButton(top, text="+", width=32, command=self._add_step).pack(side="right", padx=2)
        ctk.CTkButton(top, text="Note", width=48, command=self._edit_note).pack(side="right", padx=2)
        ctk.CTkButton(top, text="Deps", width=48, command=self._edit_deps).pack(side="right", padx=2)
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=8, pady=2)
        self._entry = ctk.CTkEntry(row, placeholder_text="Новый шаг плана…")
        self._entry.pack(side="left", fill="x", expand=True, padx=(0, 4))
        self._list = ctk.CTkTextbox(self, height=180, font=ctk.CTkFont(family="Consolas", size=12))
        self._list.pack(fill="both", expand=True, padx=8, pady=4)
        self._status = ctk.CTkLabel(self, text="", anchor="w", text_color="gray")
        self._status.pack(fill="x", padx=8, pady=2)
        # Open decisions (MODIFY/REPLAN) — resolve without second planner
        dec_fr = ctk.CTkFrame(self, fg_color="transparent")
        dec_fr.pack(fill="x", padx=8, pady=2)
        ctk.CTkLabel(dec_fr, text="Decisions", font=ctk.CTkFont(size=12, weight="bold")).pack(side="left")
        ctk.CTkButton(dec_fr, text="A", width=28, command=lambda: self._resolve_opt("A")).pack(side="right", padx=1)
        ctk.CTkButton(dec_fr, text="B", width=28, command=lambda: self._resolve_opt("B")).pack(side="right", padx=1)
        ctk.CTkButton(dec_fr, text="C", width=28, command=lambda: self._resolve_opt("C")).pack(side="right", padx=1)
        self._dec_box = ctk.CTkTextbox(self, height=72, font=ctk.CTkFont(family="Consolas", size=11))
        self._dec_box.pack(fill="x", padx=8, pady=2)
        self._open_decision_id = ""
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
                dep = s.get("depends_on") or []
                note = (s.get("note") or "")[:40]
                extra = ""
                if dep:
                    extra += f" deps={','.join(dep)}"
                if note:
                    extra += f" | {note}"
                lines.append(
                    f"[{s.get('status')}] {s.get('id')}: {s.get('action')}{extra}"
                )
            self._list.insert("1.0", "\n".join(lines) or "(пустой план)")
            dec_n = 0
            try:
                from app.plan_service import get_decision_queue
                dec_n = len(get_decision_queue(root).open_items())
            except Exception:
                dec_n = 0
            self._status.configure(
                text=f"active={data.get('active')} finished={data.get('finished')} decisions={dec_n}"
            )
            self._refresh_decisions(root)
        except Exception as e:
            self._list.insert("1.0", str(e))


    def _enqueue_selected(self) -> None:
        """Enqueue selected plan step (or first pending)."""
        root = self._root()
        if not root:
            return
        try:
            sid = self._selected_id()
            from app.plan_service import PlanService
            from app.project_workflow import ProjectWorkflow
            if sid:
                step = PlanService(root).get_step(sid)
                if step:
                    msg = str(step.get("action") or step.get("title") or "")
                    files = list(step.get("files") or [])
                    r = ProjectWorkflow(root).enqueue_step(
                        msg, files=files, source="plan_panel"
                    )
                    if r.get("ok"):
                        PlanService(root).set_step_status(
                            sid, "IN_PROGRESS", note="enqueued", task_id=str(r.get("task_id") or "")
                        )
                        self._status.configure(text=f"queued {r.get('task_id')}")
                    else:
                        self._status.configure(text=str(r.get("error") or "fail")[:60])
                    self.refresh()
                    return
            r = ProjectWorkflow(root).enqueue_first_pending()
            self._status.configure(
                text=(f"queued {r.get('task_id')}" if r.get("ok") else str(r.get("error") or "")[:60])
            )
            self.refresh()
        except Exception as exp:
            self._status.configure(text=str(exp)[:60])

    def _mark_done(self) -> None:
        root = self._root()
        sid = self._selected_id()
        if not root or not sid:
            self._status.configure(text="select a step")
            return
        try:
            from app.plan_service import PlanService
            r = PlanService(root).set_step_status(sid, "DONE", note="manual")
            self._status.configure(text="DONE" if r.get("ok") else str(r.get("error"))[:40])
            self.refresh()
        except Exception as exp:
            self._status.configure(text=str(exp)[:60])

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

    def _add_step(self) -> None:
        root = self._root()
        text = ""
        try:
            text = (self._entry.get() or "").strip()
        except Exception:
            text = ""
        if not root or not text:
            self._status.configure(text="нужны проект и текст шага")
            return
        try:
            from app.plan_service import PlanService
            s = PlanService(root).add_step(action=text)
            try:
                self._entry.delete(0, "end")
            except Exception:
                pass
            self._status.configure(text=f"added {s.get('id')}")
            self.refresh()
        except Exception as e:
            self._status.configure(text=str(e)[:120])

    def _edit_note(self) -> None:
        sid = self._selected_id()
        root = self._root()
        try:
            text = (self._entry.get() or "").strip()
        except Exception:
            text = ""
        if not sid or not root:
            self._status.configure(text="выберите шаг и текст note")
            return
        try:
            from app.plan_service import PlanService
            s = PlanService(root).edit_step(sid, note=text)
            self._status.configure(text=f"note → {sid}" if s else "нельзя")
            if s:
                try:
                    self._entry.delete(0, "end")
                except Exception:
                    pass
                self.refresh()
        except Exception as e:
            self._status.configure(text=str(e)[:120])

    def _edit_deps(self) -> None:
        sid = self._selected_id()
        root = self._root()
        try:
            text = (self._entry.get() or "").strip()
        except Exception:
            text = ""
        if not sid or not root:
            self._status.configure(text="шаг + deps через запятую")
            return
        deps = [x.strip() for x in text.split(",") if x.strip()]
        try:
            from app.plan_service import PlanService
            s = PlanService(root).edit_step(sid, depends_on=deps)
            self._status.configure(text=f"deps → {sid}" if s else "нельзя")
            if s:
                try:
                    self._entry.delete(0, "end")
                except Exception:
                    pass
                self.refresh()
        except Exception as e:
            self._status.configure(text=str(e)[:120])
