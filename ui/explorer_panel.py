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
        self._list = ctk.CTkTextbox(self, width=220, wrap="none")
        self._list.pack(fill="both", expand=True, padx=4, pady=4)
        self._list.bind("<Double-Button-1>", self._on_double)
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=4, pady=4)
        ctk.CTkButton(row, text="↻", width=36, command=self.refresh).pack(side="left")
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
