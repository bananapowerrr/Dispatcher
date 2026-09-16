# -*- coding: utf-8 -*-
"""Code intelligence — call graph & impact analysis (stdlib ast).

Optional: networkx for cycle detection. Without it, DFS-based heuristics.

Env:
  AGENTBUS_CODEINTEL=1          enable richer context injection
  AGENTBUS_CODEINTEL_MAX_FILES  default 400
"""
from __future__ import annotations

import ast
import os
import threading
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable


_SKIP_DIRS = {
    ".git", ".hg", ".svn", ".venv", "venv", "env",
    "__pycache__", ".mypy_cache", ".pytest_cache", ".ruff_cache",
    "node_modules", "dist", "build", ".tox", ".eggs",
}


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _env_flag(name: str) -> bool:
    return (os.getenv(name) or "").strip().lower() in ("1", "true", "yes", "on")


def _rel(path: Path, root: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve())).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


@dataclass
class FunctionNode:
    name: str
    qualname: str  # module.func or module.Class.method
    file: str
    lineno: int
    end_lineno: int
    calls: list[str] = field(default_factory=list)
    is_method: bool = False


class _CallVisitor(ast.NodeVisitor):
    """Collect function defs and simple call names within them."""

    def __init__(self, module: str, file_rel: str) -> None:
        self.module = module
        self.file_rel = file_rel
        self.functions: list[FunctionNode] = []
        self._stack: list[str] = []

    def _qual(self, name: str) -> str:
        if self._stack:
            return f"{self.module}.{'.'.join(self._stack)}.{name}"
        return f"{self.module}.{name}"

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._stack.append(node.name)
        self.generic_visit(node)
        self._stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._handle_fn(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._handle_fn(node)

    def _handle_fn(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        qn = self._qual(node.name)
        end = getattr(node, "end_lineno", None) or node.lineno
        fn = FunctionNode(
            name=node.name,
            qualname=qn,
            file=self.file_rel,
            lineno=int(node.lineno),
            end_lineno=int(end),
            is_method=bool(self._stack),
        )
        self.functions.append(fn)
        prev = getattr(self, "_current", None)
        self._current = fn
        self.generic_visit(node)
        self._current = prev

    def visit_Call(self, node: ast.Call) -> None:
        cur = getattr(self, "_current", None)
        if cur is not None:
            name = self._call_name(node.func)
            if name:
                cur.calls.append(name)
        self.generic_visit(node)

    @staticmethod
    def _call_name(func: ast.AST) -> str | None:
        if isinstance(func, ast.Name):
            return func.id
        if isinstance(func, ast.Attribute):
            return func.attr
        return None


class CodeIntelligence:
    """Project-level call graph built from AST."""

    def __init__(
        self,
        project_path: str | Path,
        *,
        max_files: int | None = None,
        max_file_bytes: int = 400_000,
    ) -> None:
        self.root = Path(project_path).resolve()
        self.max_files = max_files if max_files is not None else max(
            20, _env_int("AGENTBUS_CODEINTEL_MAX_FILES", 400)
        )
        self.max_file_bytes = max_file_bytes
        self.functions: dict[str, FunctionNode] = {}
        # short name → list of qualnames
        self.by_short: dict[str, list[str]] = defaultdict(list)
        # edge: caller_qual → set of callee short names
        self.out_edges: dict[str, set[str]] = defaultdict(set)
        # reverse: short callee → callers
        self.in_edges: dict[str, set[str]] = defaultdict(set)
        self._built = False
        self._lock = threading.Lock()

    def _iter_py(self) -> Iterable[Path]:
        n = 0
        try:
            paths = sorted(self.root.rglob("*.py"))
        except OSError:
            return
        for p in paths:
            if n >= self.max_files:
                break
            if any(part in _SKIP_DIRS for part in p.parts):
                continue
            try:
                if p.stat().st_size > self.max_file_bytes:
                    continue
            except OSError:
                continue
            n += 1
            yield p

    def build(self, *, force: bool = False) -> "CodeIntelligence":
        with self._lock:
            if self._built and not force:
                return self
            self.functions.clear()
            self.by_short.clear()
            self.out_edges.clear()
            self.in_edges.clear()
            for path in self._iter_py():
                rel = _rel(path, self.root)
                module = rel[:-3].replace("/", ".").replace("\\", ".")
                if module.endswith(".__init__"):
                    module = module[: -len(".__init__")]
                try:
                    src = path.read_text(encoding="utf-8", errors="replace")
                    tree = ast.parse(src, filename=str(path))
                except (OSError, SyntaxError):
                    continue
                vis = _CallVisitor(module, rel)
                try:
                    vis.visit(tree)
                except Exception:
                    continue
                for fn in vis.functions:
                    self.functions[fn.qualname] = fn
                    self.by_short[fn.name].append(fn.qualname)
                    for c in fn.calls:
                        self.out_edges[fn.qualname].add(c)
                        self.in_edges[c].add(fn.qualname)
            self._built = True
            return self

    def find_critical_functions(self, top_n: int = 10) -> list[tuple[str, int]]:
        self.build()
        scored: list[tuple[str, int]] = []
        for qn, fn in self.functions.items():
            # callers of this short name
            score = len(self.in_edges.get(fn.name, set()))
            if score:
                scored.append((qn, score))
        scored.sort(key=lambda x: -x[1])
        return scored[:top_n]

    def find_dead_code(self, *, limit: int = 30) -> list[str]:
        """Functions that call something but are never called (heuristic)."""
        self.build()
        dead: list[str] = []
        for qn, fn in self.functions.items():
            if fn.name.startswith("_") or fn.name in ("main", "__init__", "__enter__", "__exit__"):
                continue
            callers = self.in_edges.get(fn.name, set())
            # exclude self-module noise: if only called under same file still counts as live
            if not callers and self.out_edges.get(qn):
                dead.append(qn)
            if len(dead) >= limit:
                break
        return dead

    def find_circular_dependencies(self, *, limit: int = 20) -> list[list[str]]:
        self.build()
        try:
            import networkx as nx  # type: ignore

            g = nx.DiGraph()
            for qn, callees in self.out_edges.items():
                for c in callees:
                    targets = self.by_short.get(c) or []
                    for t in targets[:3]:
                        if t != qn:
                            g.add_edge(qn, t)
            cycles = []
            for cyc in nx.simple_cycles(g):
                cycles.append(cyc)
                if len(cycles) >= limit:
                    break
            return cycles
        except Exception:
            # lightweight 2-cycles via mutual short-name edges
            pairs: list[list[str]] = []
            seen: set[tuple[str, str]] = set()
            for qn, callees in self.out_edges.items():
                for c in callees:
                    for t in self.by_short.get(c, [])[:2]:
                        if qn in (self.out_edges.get(t) and {
                            x for x in self.out_edges.get(t, set())
                        } and False):
                            pass
                        # mutual: t calls back something resolving to qn's short
                        fn = self.functions.get(t)
                        if not fn:
                            continue
                        if self.functions[qn].name in self.out_edges.get(t, set()):
                            key = tuple(sorted((qn, t)))
                            if key not in seen and qn != t:
                                seen.add(key)
                                pairs.append([qn, t])
                                if len(pairs) >= limit:
                                    return pairs
            return pairs

    def get_impact_analysis(self, function_name: str) -> dict[str, Any]:
        """Who depends on this function (by short or qual name)."""
        self.build()
        short = function_name.split(".")[-1]
        callers = sorted(self.in_edges.get(short, set()))
        depth = len(callers)
        return {
            "function": function_name,
            "short": short,
            "affected": callers[:40],
            "depth": depth,
            "criticality": "high" if depth > 10 else "medium" if depth > 3 else "low",
        }

    def related_files_for(self, files: list[str], *, per_file: int = 4) -> list[str]:
        """Expand file list using call graph (callees/callers in other files)."""
        self.build()
        seeds = {str(f).replace("\\", "/") for f in (files or [])}
        if not seeds:
            return []
        extra: list[str] = []
        seen = set(seeds)
        # functions defined in seed files
        seed_fns = [fn for fn in self.functions.values() if fn.file in seeds]
        for fn in seed_fns:
            # files that call us
            for caller_qn in list(self.in_edges.get(fn.name, set()))[:per_file]:
                cf = self.functions.get(caller_qn)
                if cf and cf.file not in seen:
                    seen.add(cf.file)
                    extra.append(cf.file)
            # files we call into
            for c in list(fn.calls)[:per_file]:
                for tqn in self.by_short.get(c, [])[:2]:
                    tf = self.functions.get(tqn)
                    if tf and tf.file not in seen:
                        seen.add(tf.file)
                        extra.append(tf.file)
        return extra

    def context_snippet(self, files: list[str] | None = None, *, max_chars: int = 900) -> str:
        self.build()
        lines: list[str] = ["=== code intelligence ==="]
        crit = self.find_critical_functions(5)
        if crit:
            lines.append("top called:")
            for qn, sc in crit:
                lines.append(f"  - {qn} (callers≈{sc})")
        if files:
            related = self.related_files_for(list(files), per_file=3)
            if related:
                lines.append("related via calls:")
                for r in related[:8]:
                    lines.append(f"  - {r}")
            for f in list(files)[:3]:
                impact_bits = []
                for fn in self.functions.values():
                    if fn.file == str(f).replace("\\", "/"):
                        imp = self.get_impact_analysis(fn.qualname)
                        if imp["depth"] > 0:
                            impact_bits.append(f"{fn.name}:{imp['criticality']}")
                if impact_bits:
                    lines.append(f"impact in {f}: " + ", ".join(impact_bits[:6]))
        text = "\n".join(lines)
        return text[:max_chars]


    def signatures_snippet(
        self,
        files: list[str] | None = None,
        *,
        max_chars: int = 1500,
        per_file: int = 12,
    ) -> str:
        """Compact function signatures for seed + related files (token-cheap for 7B)."""
        self.build()
        seeds = [str(f).replace(chr(92), "/") for f in (files or [])]
        related = self.related_files_for(seeds, per_file=3) if seeds else []
        targets = list(dict.fromkeys(seeds + related))[:12]
        lines: list[str] = ["=== signatures (code graph) ==="]
        for frel in targets:
            fns = [fn for fn in self.functions.values() if fn.file == frel]
            if not fns:
                continue
            lines.append(f"# {frel}")
            for fn in fns[:per_file]:
                kind = "method" if fn.is_method else "def"
                lines.append(f"  {kind} {fn.qualname}  L{fn.lineno}")
        text = chr(10).join(lines)
        return text[:max_chars]


class CodeIntelRegistry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._map: dict[str, CodeIntelligence] = {}

    def get(self, project_path: str | Path) -> CodeIntelligence:
        key = str(Path(project_path).resolve())
        with self._lock:
            ci = self._map.get(key)
            if ci is None:
                ci = CodeIntelligence(key)
                self._map[key] = ci
            return ci


GLOBAL_CODEINTEL = CodeIntelRegistry()


def enabled() -> bool:
    return _env_flag("AGENTBUS_CODEINTEL")


if __name__ == "__main__":
    import json
    import sys

    root = sys.argv[1] if len(sys.argv) > 1 else "."
    ci = CodeIntelligence(root).build()
    print("functions", len(ci.functions))
    print("critical", ci.find_critical_functions(5))
    print("dead sample", ci.find_dead_code(limit=5))
    print(ci.context_snippet(["code_intelligence.py"]))
