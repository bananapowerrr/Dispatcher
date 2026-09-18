# -*- coding: utf-8 -*-
"""P3 Problems — aggregate task errors / verify failures for the open project."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

try:
    import customtkinter as ctk
except ImportError:  # pragma: no cover
    ctk = None  # type: ignore


def collect_problems(project_root: Path) -> list[dict[str, Any]]:
    """Scan .agentbus for error/verify artifacts — no live worker required."""
    out: list[dict[str, Any]] = []
    base = Path(project_root) / ".agentbus"
    if not base.is_dir():
        return out
    for sub in ("errors", "history", "quarantine", "verify"):
        d = base / sub
        if not d.is_dir():
            continue
        for path in sorted(d.glob("*.json"))[:40]:
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                out.append({"kind": "corrupt", "file": "", "message": path.name})
                continue
            if not isinstance(data, dict):
                continue
            err = str(data.get("error") or data.get("stderr") or data.get("reason") or "")
            status = str(data.get("status") or "")
            if sub == "history" and status.upper() in ("DONE", "SUCCESS", "") and not err:
                continue
            if not err and status.upper() not in ("ERROR", "FAILED", "FAIL"):
                continue
            files = data.get("files") or []
            f0 = files[0] if isinstance(files, list) and files else ""
            out.append({
                "kind": sub if sub != "history" else "task",
                "file": str(f0),
                "message": (err or status or path.stem)[:300],
                "task_id": str(data.get("id") or path.stem),
            })
    try:
        from intelligence.living_plan import load_living_plan
        plan = load_living_plan(project_root)
        for s in plan.steps:
            if str(s.status).upper() == "ERROR":
                out.append({
                    "kind": "plan",
                    "file": (s.files[0] if s.files else ""),
                    "message": f"{s.id}: {s.action} — {s.reason or 'ERROR'}",
                    "task_id": s.id,
                })
    except Exception:
        pass
    return out[:80]


class ProblemsPanel(ctk.CTkFrame if ctk else object):  # type: ignore
    def __init__(
        self,
        master,
        *,
        get_project: Callable[[], str] | None = None,
        on_open_file: Callable[[str], None] | None = None,
        on_open_task: Callable[[str], None] | None = None,
        **kwargs: Any,
    ):
        if ctk is None:
            raise RuntimeError("customtkinter required")
        super().__init__(master, **kwargs)
        self._get_project = get_project or (lambda: "")
        self._on_open = on_open_file
        self._on_open_task = on_open_task
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=8, pady=4)
        ctk.CTkLabel(top, text="Problems", font=ctk.CTkFont(size=14, weight="bold")).pack(side="left")
        ctk.CTkButton(top, text="↻", width=36, command=self.refresh).pack(side="right")
        self._list = ctk.CTkTextbox(self, font=ctk.CTkFont(family="Consolas", size=12))
        self._list.pack(fill="both", expand=True, padx=8, pady=4)
        self._list.bind("<Double-Button-1>", self._on_double)
        self._status = ctk.CTkLabel(self, text="", anchor="w", text_color="gray")
        self._status.pack(fill="x", padx=8, pady=2)
        self._rows: list[dict[str, Any]] = []
        self.after(500, self.refresh)

    def _root(self) -> str:
        try:
            r = self._get_project()
            return (r() if callable(r) else r) or ""
        except Exception:
            return ""

    def refresh(self) -> None:
        root = self._root()
        self._list.delete("1.0", "end")
        self._rows = []
        if not root:
            self._list.insert("1.0", "(нет проекта)")
            return
        items = collect_problems(Path(root))
        self._rows = items
        if not items:
            self._list.insert("1.0", "(чисто — ошибок не найдено)")
            self._status.configure(text="0 problems")
            return
        lines = [
            f"{i}. [{it.get('kind')}] {it.get('file') or '-'}  {it.get('message', '')[:120]}"
            for i, it in enumerate(items, 1)
        ]
        self._list.insert("1.0", "\n".join(lines))
        self._status.configure(text=f"{len(items)} problem(s)")

    def _on_double(self, _event=None) -> None:
        """Open file in editor; if task_id present — also notify task open."""
        try:
            line = self._list.get("insert linestart", "insert lineend").strip()
            if not line or not line[0].isdigit():
                return
            idx = int(line.split(".", 1)[0]) - 1
            if 0 <= idx < len(self._rows):
                row = self._rows[idx]
                f = row.get("file") or ""
                tid = str(row.get("task_id") or "")
                if f and self._on_open:
                    self._on_open(f)
                if tid and getattr(self, "_on_open_task", None):
                    try:
                        self._on_open_task(tid)
                    except Exception:
                        pass
        except Exception:
            pass
