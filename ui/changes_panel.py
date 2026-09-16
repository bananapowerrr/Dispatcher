# -*- coding: utf-8 -*-
"""FC-40 Changes panel — workspace git changes via ChangesService."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

try:
    import customtkinter as ctk
except ImportError:  # pragma: no cover
    ctk = None  # type: ignore


class ChangesPanel(ctk.CTkFrame if ctk else object):  # type: ignore
    """List modified files; open diff / file."""

    def __init__(
        self,
        master,
        *,
        get_project: Callable[[], str] | None = None,
        on_review_file: Callable[[str, str], None] | None = None,
        on_open_file: Callable[[str], None] | None = None,
        **kwargs: Any,
    ):
        if ctk is None:
            raise RuntimeError("customtkinter required")
        super().__init__(master, **kwargs)
        self._get_project = get_project or (lambda: "")
        self._on_review = on_review_file  # (path, diff_text)
        self._on_open = on_open_file
        self._paths: list[str] = []

        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=8, pady=4)
        ctk.CTkLabel(top, text="Changes", font=ctk.CTkFont(size=14, weight="bold")).pack(side="left")
        self._count = ctk.CTkLabel(top, text="", text_color="gray")
        self._count.pack(side="left", padx=8)
        ctk.CTkButton(top, text="↻", width=36, command=self.refresh).pack(side="right")

        self._list = ctk.CTkTextbox(self, height=120, wrap="none", font=ctk.CTkFont(family="Consolas", size=12))
        self._list.pack(fill="both", expand=True, padx=8, pady=4)
        self._list.bind("<Double-Button-1>", self._on_double)

        btn = ctk.CTkFrame(self, fg_color="transparent")
        btn.pack(fill="x", padx=8, pady=6)
        ctk.CTkButton(btn, text="Review", width=90, command=self.review_selected).pack(side="left", padx=4)
        ctk.CTkButton(btn, text="Open", width=90, command=self.open_selected).pack(side="left", padx=4)
        ctk.CTkButton(btn, text="Review all", width=100, command=self.review_all).pack(side="left", padx=4)

        self._status = ctk.CTkLabel(self, text="", anchor="w", text_color="gray")
        self._status.pack(fill="x", padx=8, pady=(0, 4))

    def _root(self) -> str:
        try:
            r = self._get_project()
            return (r() if callable(r) else r) or ""
        except Exception:
            return ""

    def refresh(self) -> None:
        root = self._root().strip()
        self._list.delete("1.0", "end")
        self._paths = []
        if not root:
            self._count.configure(text="")
            self._list.insert("1.0", "(выберите проект)")
            return
        try:
            import sys
            base = Path(__file__).resolve().parents[1]
            if str(base / "src") not in sys.path:
                sys.path.insert(0, str(base / "src"))
            from app.changes_service import ChangesService
            files = ChangesService(root).list_changes()
            self._paths = [f["path"] for f in files]
            if not files:
                self._list.insert("1.0", "(нет изменений в git)")
                self._count.configure(text="0")
                self._status.configure(text="")
                return
            lines = [f"{f.get('status', 'M'):2}  {f['path']}" for f in files]
            self._list.insert("1.0", "\n".join(lines))
            self._count.configure(text=str(len(files)))
            self._status.configure(text=f"{len(files)} file(s)")
        except Exception as exp:
            self._list.insert("1.0", f"Ошибка: {exp}")
            self._status.configure(text=str(exp)[:120])

    def _selected_path(self) -> str:
        try:
            idx = int(self._list.index("insert").split(".")[0]) - 1
            if 0 <= idx < len(self._paths):
                return self._paths[idx]
        except Exception:
            pass
        return self._paths[0] if self._paths else ""

    def _diff_for(self, path: str) -> str:
        root = self._root().strip()
        if not root or not path:
            return ""
        import sys
        base = Path(__file__).resolve().parents[1]
        if str(base / "src") not in sys.path:
            sys.path.insert(0, str(base / "src"))
        from app.changes_service import ChangesService
        return ChangesService(root).diff_file(path)

    def review_selected(self) -> None:
        path = self._selected_path()
        if not path:
            self._status.configure(text="Нет файла")
            return
        diff = self._diff_for(path)
        if self._on_review:
            self._on_review(path, diff or f"# empty diff: {path}\n")
        self._status.configure(text=f"Review: {path}")

    def review_all(self) -> None:
        root = self._root().strip()
        if not root:
            return
        import sys
        base = Path(__file__).resolve().parents[1]
        if str(base / "src") not in sys.path:
            sys.path.insert(0, str(base / "src"))
        from app.changes_service import ChangesService
        cs = ChangesService(root)
        blocks = []
        for f in cs.list_changes():
            d = cs.diff_file(f["path"])
            blocks.append(f"=== {f['path']} ===\n{d or '(binary or empty)'}")
        text = "\n\n".join(blocks) if blocks else "(нет изменений)"
        if self._on_review:
            self._on_review("", text)
        self._status.configure(text="Review all")

    def open_selected(self) -> None:
        path = self._selected_path()
        if path and self._on_open:
            self._on_open(path)

    def _on_double(self, _event=None) -> None:
        self.review_selected()
