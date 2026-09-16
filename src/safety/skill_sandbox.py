# -*- coding: utf-8 -*-
"""AST sandbox validation for auto-generated skill plugins.

Rejects code that imports dangerous modules, uses exec/eval/open for write,
or defines top-level side effects beyond a single skill_* function.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass, field
from typing import Any


FORBIDDEN_IMPORTS = frozenset({
    "os", "sys", "subprocess", "socket", "ctypes", "importlib",
    "shutil", "pathlib", "pickle", "requests", "urllib", "http",
    "multiprocessing", "threading", "pty", "fcntl", "signal",
})

FORBIDDEN_NAMES = frozenset({
    "exec", "eval", "compile", "__import__", "open", "input",
    "breakpoint", "exit", "quit", "getattr", "setattr", "delattr",
    "globals", "locals", "vars", "memoryview",
})

ALLOWED_IMPORTS = frozenset({
    "re", "json", "ast", "collections", "dataclasses", "typing",
    "functools", "itertools", "textwrap", "difflib", "hashlib",
    "math", "string", "copy",
})


@dataclass
class ValidationResult:
    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    skill_name: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "skill_name": self.skill_name,
        }


class SkillSandbox:
    """Static checks only — no execution of candidate code."""

    def validate(self, source: str) -> ValidationResult:
        errors: list[str] = []
        warnings: list[str] = []
        skill_name: str | None = None
        if not (source or "").strip():
            return ValidationResult(False, errors=["empty source"])
        try:
            tree = ast.parse(source)
        except SyntaxError as exc:
            return ValidationResult(False, errors=[f"SyntaxError: {exc}"])

        skill_funcs: list[str] = []
        for node in tree.body:
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = []
                if isinstance(node, ast.Import):
                    names = [a.name.split(".")[0] for a in node.names]
                else:
                    if node.module:
                        names = [node.module.split(".")[0]]
                for n in names:
                    if n in FORBIDDEN_IMPORTS:
                        errors.append(f"forbidden import: {n}")
                    elif n not in ALLOWED_IMPORTS and n not in ("__future__",):
                        warnings.append(f"non-whitelisted import: {n}")
            elif isinstance(node, ast.FunctionDef):
                if node.name.startswith("skill_"):
                    skill_funcs.append(node.name)
                else:
                    warnings.append(f"non-skill function at module level: {node.name}")
            elif isinstance(node, (ast.ClassDef, ast.Assign, ast.AnnAssign, ast.Expr)):
                if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
                    continue  # docstring / string
                if isinstance(node, ast.Assign):
                    warnings.append("module-level assignment")
                elif isinstance(node, ast.ClassDef):
                    warnings.append(f"module-level class: {node.name}")
            else:
                warnings.append(f"unexpected top-level: {type(node).__name__}")

        if not skill_funcs:
            errors.append("no skill_* function defined")
        elif len(skill_funcs) > 1:
            warnings.append(f"multiple skill functions: {skill_funcs}")
        else:
            skill_name = skill_funcs[0]

        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                fn = node.func
                name = None
                if isinstance(fn, ast.Name):
                    name = fn.id
                elif isinstance(fn, ast.Attribute):
                    name = fn.attr
                if name in FORBIDDEN_NAMES:
                    errors.append(f"forbidden call: {name}")
            if isinstance(node, ast.Name) and node.id in ("os", "sys", "subprocess"):
                # bare name use without import still suspicious in generated code
                if isinstance(node.ctx, ast.Load):
                    errors.append(f"forbidden name load: {node.id}")

        return ValidationResult(
            ok=not errors,
            errors=errors,
            warnings=warnings,
            skill_name=skill_name,
        )


def validate_skill_source(source: str) -> ValidationResult:
    return SkillSandbox().validate(source)
