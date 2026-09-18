# -*- coding: utf-8 -*-
"""P4 Search — project text search via FilesService.search."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

try:
    import customtkinter as ctk
except ImportError:  # pragma: no cover
    ctk = None  # type: ignore


class SearchPanel(ctk.CTkFrame if ctk else object):  # type: ignore
    def __init__(
        self,
        master,
        *,
        get_project: Callable[[], str] | None = None,
        on_open_file: Callable[[str], None] | None = None,
        **kwargs: Any,
    ):
        if ctk is None:
            raise RuntimeError("customtkinter required")
        super().__init__(master, **kwargs)
        self._get_project = get_project or (lambda: "")
        self._on_open = on_open_file
        self._hits: list[dict[str, Any]] = []

        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=8, pady=6)
        self._entry = ctk.CTkEntry(row, placeholder_text="Search in project…")
        self._entry.pack(side="left", fill="x", expand=True, padx=(0, 4))
        self._entry.bind("<Return>", lambda e: self.run_search())
        ctk.CTkButton(row, text="Search", width=70, command=self.run_search).pack(side="right")

        self._list = ctk.CTkTextbox(self, font=ctk.CTkFont(family="Consolas", size=12))
        self._list.pack(fill="both", expand=True, padx=8, pady=4)
        self._list.bind("<Double-Button-1>", self._on_double)
        self._status = ctk.CTkLabel(self, text="", anchor="w", text_color="gray")
        self._status.pack(fill="x", padx=8, pady=2)

    def _root(self) -> str:
        try:
            r = self._get_project()
            return (r() if callable(r) else r) or ""
        except Exception:
            return ""

    def run_search(self) -> None:
        root = self._root()
        try:
            q = (self._entry.get() or "").strip()
        except Exception:
            q = ""
        self._list.delete("1.0", "end")
        self._hits = []
        if not root:
            self._list.insert("1.0", "(нет проекта)")
            return
        if not q:
            self._list.insert("1.0", "(введите запрос)")
            return
        try:
            import sys
            base = Path(__file__).resolve().parents[1]
            if str(base / "src") not in sys.path:
                sys.path.insert(0, str(base / "src"))
            from app.files_service import FilesService
            hits = FilesService(root).search(q, max_hits=80)
            self._hits = hits
            if not hits:
                self._list.insert("1.0", "ничего не найдено")
                self._status.configure(text="0 hits")
                return
            lines = [f"{h['path']}:{h['line']}: {h['text']}" for h in hits]
            self._list.insert("1.0", "\n".join(lines))
            self._status.configure(text=f"{len(hits)} hit(s)")
        except Exception as exp:
            self._list.insert("1.0", str(exp))
            self._status.configure(text="error")

    def _on_double(self, _event=None) -> None:
        try:
            line = self._list.get("insert linestart", "insert lineend").strip()
            if ":" not in line:
                return
            path = line.split(":", 1)[0]
            if path and self._on_open:
                self._on_open(path)
        except Exception:
            pass

    def refresh(self) -> None:
        pass

    def focus_search(self) -> None:
        try:
            self._entry.focus_set()
        except Exception:
            pass
