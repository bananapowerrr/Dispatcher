# -*- coding: utf-8 -*-
"""Control-flow style impact analysis using stdlib ast (+ optional networkx)."""
from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class CFGNode:
    id: int
    type: str  # entry | block | branch | exit
    code: str
    line_start: int
    line_end: int


@dataclass
class FunctionCFG:
    name: str
    nodes: dict[int, CFGNode] = field(default_factory=dict)
    edges: list[tuple[int, int, str]] = field(default_factory=list)  # (src, dst, label)

    def successors(self, nid: int) -> list[int]:
        return [d for s, d, _ in self.edges if s == nid]

    def descendants(self, nid: int) -> set[int]:
        seen: set[int] = set()
        stack = list(self.successors(nid))
        while stack:
            n = stack.pop()
            if n in seen:
                continue
            seen.add(n)
            stack.extend(self.successors(n))
        return seen


class CFGBuilder:
    """Build a lightweight CFG per function from ast."""

    def build_file(self, path: str | Path) -> list[FunctionCFG]:
        text = Path(path).read_text(encoding="utf-8")
        tree = ast.parse(text)
        out: list[FunctionCFG] = []
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                out.append(self.build_function(node))
            elif isinstance(node, ast.ClassDef):
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        cfg = self.build_function(item)
                        cfg.name = f"{node.name}.{cfg.name}"
                        out.append(cfg)
        return out

    def build_function(self, func: ast.FunctionDef | ast.AsyncFunctionDef) -> FunctionCFG:
        cfg = FunctionCFG(name=func.name)
        nid = 0

        def new_node(ntype: str, code: str, line: int) -> int:
            nonlocal nid
            i = nid
            nid += 1
            cfg.nodes[i] = CFGNode(i, ntype, code, line, line)
            return i

        entry = new_node("entry", f"def {func.name}", getattr(func, "lineno", 0) or 0)
        current = entry

        def process_stmts(stmts: list[ast.stmt], prev: int) -> int:
            cur = prev
            for stmt in stmts:
                line = getattr(stmt, "lineno", 0) or 0
                if isinstance(stmt, ast.If):
                    br = new_node("branch", "if", line)
                    cfg.edges.append((cur, br, ""))
                    t = new_node("block", "then", line)
                    cfg.edges.append((br, t, "True"))
                    t_end = process_stmts(list(stmt.body), t)
                    f_end = br
                    if stmt.orelse:
                        f = new_node("block", "else", line)
                        cfg.edges.append((br, f, "False"))
                        f_end = process_stmts(list(stmt.orelse), f)
                    merge = new_node("block", "merge", getattr(stmt, "end_lineno", line) or line)
                    cfg.edges.append((t_end, merge, ""))
                    if f_end != br:
                        cfg.edges.append((f_end, merge, ""))
                    else:
                        cfg.edges.append((br, merge, "False"))
                    cur = merge
                elif isinstance(stmt, (ast.For, ast.While)):
                    loop = new_node("branch", type(stmt).__name__.lower(), line)
                    cfg.edges.append((cur, loop, ""))
                    body = new_node("block", "loop_body", line)
                    cfg.edges.append((loop, body, "iter"))
                    body_end = process_stmts(list(stmt.body), body)
                    cfg.edges.append((body_end, loop, "back"))
                    after = new_node("block", "after_loop", getattr(stmt, "end_lineno", line) or line)
                    cfg.edges.append((loop, after, "exit"))
                    cur = after
                else:
                    blk = new_node("block", type(stmt).__name__, line)
                    cfg.edges.append((cur, blk, ""))
                    # extend line_end if possible
                    end = getattr(stmt, "end_lineno", line) or line
                    cfg.nodes[blk].line_end = end
                    cur = blk
            return cur

        last = process_stmts(list(func.body), current)
        exit_id = new_node("exit", "exit", getattr(func, "end_lineno", 0) or 0)
        cfg.edges.append((last, exit_id, ""))
        return cfg


class ImpactAnalyzer:
    """Map a changed line to reachable lines via function CFGs."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.cfgs = CFGBuilder().build_file(self.path)

    def affected_lines(self, changed_line: int) -> list[int]:
        affected: set[int] = set()
        for cfg in self.cfgs:
            for nid, node in cfg.nodes.items():
                if node.line_start <= changed_line <= node.line_end:
                    for desc in cfg.descendants(nid) | {nid}:
                        dn = cfg.nodes[desc]
                        for ln in range(dn.line_start, max(dn.line_start, dn.line_end) + 1):
                            if ln > 0:
                                affected.add(ln)
        return sorted(affected)

    def summary(self, changed_line: int) -> dict[str, Any]:
        lines = self.affected_lines(changed_line)
        return {
            "file": str(self.path),
            "changed_line": changed_line,
            "affected_lines": lines[:80],
            "count": len(lines),
            "functions": [c.name for c in self.cfgs],
        }
