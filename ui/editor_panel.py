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
    __slots__ = ("path", "original", "dirty", "buffer")

    def __init__(self, path: str, original: str):
        self.path = path
        self.original = original
        self.dirty = False
        self.buffer: str | None = None


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
        # P3 IDE foundation shortcuts
        self._text.bind("<Control-s>", lambda e: (self.save_current(), "break")[1])
        self._text.bind("<Control-S>", lambda e: (self.save_current(), "break")[1])
        self.bind_all("<Control-w>", self._on_ctrl_w)
        self.bind_all("<Control-W>", self._on_ctrl_w)
        self.bind_all("<Control-Tab>", self._on_ctrl_tab)
        self.bind_all("<Control-ISO_Left_Tab>", lambda e: self._on_ctrl_tab(e, reverse=True))

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
            st.buffer = None
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
            # sync buffer from widget
            try:
                self._tabs[path].buffer = self._text.get("1.0", "end-1c")
                self._tabs[path].dirty = True
            except Exception:
                pass
            if not self._confirm_discard(path):
                return
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
            st_old.buffer = buf
        self._current = path
        st = self._tabs[path]
        body = st.buffer if st.buffer is not None else st.original
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

    def _confirm_discard(self, path: str) -> bool:
        """Ask save/discard/cancel for dirty tab. Returns True if close may proceed."""
        try:
            from tkinter import messagebox
            r = messagebox.askyesnocancel(
                "Несохранённые изменения",
                f"Файл изменён:\n{path}\n\nСохранить перед закрытием?",
                parent=self.winfo_toplevel(),
            )
        except Exception:
            # headless / no dialog — keep content, refuse silent loss
            self._status.configure(text="есть несохранённые изменения — Ctrl+S")
            return False
        if r is None:
            return False  # cancel
        if r is True:
            return self.save_current()
        return True  # discard

    def _show_find(self, replace: bool = False) -> None:
        if not self._find_visible:
            self._find_frame.pack(fill="x", padx=8, pady=2, before=self._text)
            self._find_visible = True
        try:
            if replace and hasattr(self, "_repl_entry"):
                self._repl_entry.focus_set()
            else:
                self._find_entry.focus_set()
                self._find_entry.select_range(0, "end")
        except Exception:
            pass
        self._find_pos = "1.0"

    def _hide_find(self) -> None:
        if self._find_visible:
            try:
                self._find_frame.pack_forget()
            except Exception:
                pass
            self._find_visible = False
        try:
            self._text.tag_remove("find_hit", "1.0", "end")
            self._text.focus_set()
        except Exception:
            pass

    def _find_next(self) -> None:
        try:
            needle = (self._find_entry.get() or "").strip()
        except Exception:
            needle = ""
        if not needle:
            self._status.configure(text="введите строку поиска")
            return
        try:
            self._text.tag_remove("find_hit", "1.0", "end")
            start = self._find_pos or "1.0"
            idx = self._text.search(needle, start, stopindex="end", nocase=True)
            if not idx:
                # wrap
                idx = self._text.search(needle, "1.0", stopindex="end", nocase=True)
            if not idx:
                self._status.configure(text="не найдено")
                return
            end = f"{idx}+{len(needle)}c"
            self._text.tag_add("find_hit", idx, end)
            self._text.tag_config("find_hit", background="#5a5a20")
            self._text.see(idx)
            self._find_pos = end
            self._status.configure(text=f"найдено @ {idx}")
        except Exception as exp:
            self._status.configure(text=f"find: {exp}")

    def _goto_line(self) -> None:
        try:
            from tkinter import simpledialog
            n = simpledialog.askinteger(
                "Перейти к строке",
                "Номер строки:",
                parent=self.winfo_toplevel(),
                minvalue=1,
            )
        except Exception:
            n = None
        if not n:
            return
        try:
            self._text.see(f"{n}.0")
            self._text.mark_set("insert", f"{n}.0")
            self._status.configure(text=f"строка {n}")
        except Exception as exp:
            self._status.configure(text=str(exp)[:80])

    def dirty_paths(self) -> list[str]:
        """Relative paths with unsaved changes (for exit guard)."""
        out: list[str] = []
        # flush current buffer
        if self._current and self._current in self._tabs:
            try:
                body = self._text.get("1.0", "end-1c")
                st = self._tabs[self._current]
                st.buffer = body
                st.dirty = body != st.original
            except Exception:
                pass
        for path, st in self._tabs.items():
            if st.dirty:
                out.append(path)
        return out

    def _replace_one(self) -> None:
        try:
            needle = (self._find_entry.get() or "")
            repl = self._repl_entry.get() if hasattr(self, "_repl_entry") else ""
        except Exception:
            return
        if not needle:
            return
        try:
            # ensure selection is current hit
            ranges = self._text.tag_ranges("find_hit")
            if len(ranges) >= 2:
                self._text.delete(ranges[0], ranges[1])
                self._text.insert(ranges[0], repl)
                self._find_pos = str(ranges[0])
                self._on_modified()
                self._find_next()
                self._status.configure(text="replaced 1")
            else:
                self._find_next()
        except Exception as exp:
            self._status.configure(text=f"replace: {exp}")

    def _replace_all(self) -> None:
        try:
            needle = (self._find_entry.get() or "")
            repl = self._repl_entry.get() if hasattr(self, "_repl_entry") else ""
        except Exception:
            return
        if not needle:
            return
        try:
            body = self._text.get("1.0", "end-1c")
            count = body.count(needle)
            if count == 0:
                # case-insensitive count via search loop
                n = 0
                idx = "1.0"
                while True:
                    idx = self._text.search(needle, idx, stopindex="end", nocase=True)
                    if not idx:
                        break
                    n += 1
                    idx = f"{idx}+1c"
                if n == 0:
                    self._status.configure(text="не найдено")
                    return
                # rebuild via iterative replace
                idx = "1.0"
                while True:
                    idx = self._text.search(needle, idx, stopindex="end", nocase=True)
                    if not idx:
                        break
                    end = f"{idx}+{len(needle)}c"
                    self._text.delete(idx, end)
                    self._text.insert(idx, repl)
                    idx = f"{idx}+{len(repl)}c"
                self._on_modified()
                self._status.configure(text=f"replaced {n}")
                return
            body2 = body.replace(needle, repl)
            self._text.delete("1.0", "end")
            self._text.insert("1.0", body2)
            self._on_modified()
            self._status.configure(text=f"replaced {count}")
        except Exception as exp:
            self._status.configure(text=f"replace all: {exp}")
