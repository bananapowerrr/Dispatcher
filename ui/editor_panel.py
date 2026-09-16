# -*- coding: utf-8 -*-
"""FC-39 Editor shell — multi-tab text editor via FilesService.

Not a full IDE editor (no LSP). Provides: open/save, dirty flag, tabs,
active path for AgentService context.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

try:
    import customtkinter as ctk
except ImportError:  # pragma: no cover
    ctk = None  # type: ignore


class _TabState:
    __slots__ = ("path", "original", "dirty")

    def __init__(self, path: str, original: str):
        self.path = path
        self.original = original
        self.dirty = False


class EditorPanel(ctk.CTkFrame if ctk else object):  # type: ignore
    """Center editor with simple tab strip."""

    def __init__(
        self,
        master,
        *,
        get_project: Callable[[], str] | None = None,
        on_active_change: Callable[[str, str], None] | None = None,
        **kwargs: Any,
    ):
        if ctk is None:
            raise RuntimeError("customtkinter required")
        super().__init__(master, **kwargs)
        self._get_project = get_project or (lambda: "")
        self._on_active = on_active_change  # (path, selection_or_empty)
        self._tabs: dict[str, _TabState] = {}
        self._order: list[str] = []
        self._current: str = ""

        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=4, pady=2)
        self._tab_bar = ctk.CTkFrame(top, fg_color="transparent")
        self._tab_bar.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(top, text="💾", width=36, command=self.save_current).pack(side="right", padx=2)
        ctk.CTkButton(top, text="×", width=36, command=self.close_current).pack(side="right", padx=2)

        self._path_label = ctk.CTkLabel(self, text="", anchor="w", text_color="gray")
        self._path_label.pack(fill="x", padx=8)

        self._text = ctk.CTkTextbox(self, wrap="none", font=ctk.CTkFont(family="Consolas", size=13))
        self._text.pack(fill="both", expand=True, padx=4, pady=4)
        self._text.bind("<<Modified>>", self._on_modified)
        self._text.bind("<KeyRelease>", self._notify_active)
        self._text.bind("<ButtonRelease-1>", self._notify_active)

        self._status = ctk.CTkLabel(self, text="", anchor="w", text_color="gray")
        self._status.pack(fill="x", padx=8, pady=(0, 4))

    # --- public API ---

    def open_file(self, rel_path: str) -> bool:
        root = (self._get_project() or "").strip()
        if not root or not rel_path:
            self._status.configure(text="Нет проекта или пути")
            return False
        rel_path = rel_path.replace("\\", "/").lstrip("./")
        if rel_path in self._tabs:
            self._switch(rel_path)
            return True
        try:
            import sys
            base = Path(__file__).resolve().parents[1]
            if str(base / "src") not in sys.path:
                sys.path.insert(0, str(base / "src"))
            from app.files_service import FilesService
            content = FilesService(root).read_text(rel_path)
        except Exception as exp:
            self._status.configure(text=f"Не открыть: {exp}")
            return False
        self._tabs[rel_path] = _TabState(rel_path, content)
        self._order.append(rel_path)
        self._rebuild_tab_bar()
        self._switch(rel_path)
        return True

    def save_current(self) -> bool:
        if not self._current or self._current not in self._tabs:
            return False
        root = (self._get_project() or "").strip()
        if not root:
            return False
        body = self._text.get("1.0", "end-1c")
        try:
            import sys
            base = Path(__file__).resolve().parents[1]
            if str(base / "src") not in sys.path:
                sys.path.insert(0, str(base / "src"))
            from app.files_service import FilesService
            FilesService(root).write_text(self._current, body)
            st = self._tabs[self._current]
            st.original = body
            st.dirty = False
            self._rebuild_tab_bar()
            self._path_label.configure(text=self._current)
            self._status.configure(text="Сохранено")
            return True
        except Exception as exp:
            self._status.configure(text=f"Ошибка записи: {exp}")
            return False

    def close_current(self) -> None:
        if not self._current:
            return
        path = self._current
        if path in self._tabs and self._tabs[path].dirty:
            # soft: still close (product can add confirm dialog later)
            pass
        self._tabs.pop(path, None)
        if path in self._order:
            self._order.remove(path)
        self._current = self._order[-1] if self._order else ""
        self._rebuild_tab_bar()
        if self._current:
            self._switch(self._current)
        else:
            self._text.delete("1.0", "end")
            self._path_label.configure(text="")
            self._notify_active()

    def active_path(self) -> str:
        return self._current

    def selected_text(self) -> str:
        try:
            if self._text.tag_ranges("sel"):
                return self._text.get("sel.first", "sel.last")
        except Exception:
            pass
        return ""

    def get_context(self) -> dict[str, Any]:
        return {
            "active_file": self._current,
            "selection": self.selected_text(),
            "dirty": bool(self._tabs.get(self._current) and self._tabs[self._current].dirty),
        }

    # --- internals ---

    def _switch(self, path: str) -> None:
        # persist current buffer
        if self._current and self._current in self._tabs:
            buf = self._text.get("1.0", "end-1c")
            st_old = self._tabs[self._current]
            st_old.dirty = buf != st_old.original
            # keep unsaved buffer in a side field via original only when not dirty;
            # store buffer on dirty by overwriting a runtime attr
            st_old._buffer = buf  # type: ignore[attr-defined]
        self._current = path
        st = self._tabs[path]
        body = getattr(st, "_buffer", None) or st.original
        self._text.delete("1.0", "end")
        self._text.insert("1.0", body)
        st.dirty = body != st.original
        try:
            self._text.edit_modified(False)
        except Exception:
            pass
        mark = " •" if st.dirty else ""
        self._path_label.configure(text=f"{path}{mark}")
        self._rebuild_tab_bar()
        self._notify_active()
        self._status.configure(text="")

    def _rebuild_tab_bar(self) -> None:
        for w in self._tab_bar.winfo_children():
            w.destroy()
        for path in self._order:
            st = self._tabs[path]
            name = Path(path).name + (" *" if st.dirty else "")
            btn = ctk.CTkButton(
                self._tab_bar,
                text=name,
                width=max(60, min(140, 10 * len(name))),
                height=28,
                fg_color=("#3a7ebf" if path == self._current else "transparent"),
                command=lambda p=path: self._switch(p),
            )
            btn.pack(side="left", padx=2)

    def _on_modified(self, _event=None) -> None:
        try:
            if not self._text.edit_modified():
                return
        except Exception:
            return
        if self._current and self._current in self._tabs:
            body = self._text.get("1.0", "end-1c")
            st = self._tabs[self._current]
            st.dirty = body != st.original
            self._rebuild_tab_bar()
            mark = " •" if st.dirty else ""
            self._path_label.configure(text=f"{self._current}{mark}")
        try:
            self._text.edit_modified(False)
        except Exception:
            pass

    def _notify_active(self, _event=None) -> None:
        if self._on_active:
            try:
                self._on_active(self._current, self.selected_text())
            except Exception:
                pass
