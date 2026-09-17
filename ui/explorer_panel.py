# -*- coding: utf-8 -*-
"""FC-38/39 Explorer — project tree via FilesService."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

try:
    import customtkinter as ctk
except ImportError:  # pragma: no cover
    ctk = None  # type: ignore


class ExplorerPanel(ctk.CTkFrame if ctk else object):  # type: ignore
    """Left sidebar file tree."""

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
        ctk.CTkLabel(self, text="Explorer", font=ctk.CTkFont(weight="bold")).pack(
            anchor="w", padx=8, pady=(8, 4)
        )
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=4, pady=2)
        ctk.CTkButton(row, text="+f", width=32, command=self._new_file).pack(side="left", padx=1)
        ctk.CTkButton(row, text="+d", width=32, command=self._new_dir).pack(side="left", padx=1)
        ctk.CTkButton(row, text="↻", width=32, command=self.refresh).pack(side="left", padx=1)
        self._name_entry = ctk.CTkEntry(row, placeholder_text="name…", width=100)
        self._name_entry.pack(side="left", fill="x", expand=True, padx=2)
        self._list = ctk.CTkTextbox(self, width=220, wrap="none")
        self._list.pack(fill="both", expand=True, padx=4, pady=4)
        self._list.bind("<Double-Button-1>", self._on_double)
        self._paths: list[str] = []

    def refresh(self) -> None:
        root = (self._get_project() or "").strip()
        self._list.delete("1.0", "end")
        self._paths = []
        if not root:
            self._list.insert("1.0", "(выберите проект)")
            return
        try:
            import sys
            base = Path(__file__).resolve().parents[1]
            if str(base / "src") not in sys.path:
                sys.path.insert(0, str(base / "src"))
            from app.files_service import FilesService
            fs = FilesService(root)
            tree = fs.tree(max_depth=5, max_entries=500)
            lines: list[str] = []

            def render(nodes: list[dict], indent: int = 0) -> None:
                for n in nodes:
                    prefix = "  " * indent
                    if n.get("type") == "dir":
                        lines.append(f"{prefix}📁 {n['name']}")
                        self._paths.append(n.get("path") or "")
                        render(n.get("children") or [], indent + 1)
                    else:
                        lines.append(f"{prefix}📄 {n['name']}")
                        self._paths.append(n.get("path") or "")

            render(tree)
            self._list.insert("1.0", "\n".join(lines) if lines else "(пусто)")
        except Exception as exp:
            self._list.insert("1.0", f"Ошибка: {exp}")

    def _on_double(self, _event=None) -> None:
        try:
            idx = self._list.index("insert").split(".")[0]
            line_no = int(idx) - 1
            if 0 <= line_no < len(self._paths):
                path = self._paths[line_no]
                if path and self._on_open and not path.endswith("/"):
                    # skip pure dir markers without extension heuristic
                    if "." in Path(path).name or path.endswith(".py"):
                        self._on_open(path)
        except Exception:
            pass

    def _entry_name(self) -> str:
        try:
            return (self._name_entry.get() or "").strip().replace("\\", "/").lstrip("/")
        except Exception:
            return ""

    def _project_root(self) -> Path | None:
        try:
            r = self._get_project()
            s = (r() if callable(r) else r) or ""
            if not s:
                return None
            return Path(s)
        except Exception:
            return None

    def _new_file(self) -> None:
        root = self._project_root()
        name = self._entry_name()
        if not root or not name:
            return
        path = root / name
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            if not path.exists():
                path.write_text("", encoding="utf-8")
            if self._on_open:
                self._on_open(name)
            self.refresh()
        except Exception:
            pass

    def _new_dir(self) -> None:
        root = self._project_root()
        name = self._entry_name()
        if not root or not name:
            return
        try:
            (root / name).mkdir(parents=True, exist_ok=True)
            self.refresh()
        except Exception:
            pass
