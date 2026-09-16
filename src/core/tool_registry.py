# -*- coding: utf-8 -*-
"""Unified Tool Registry — one schema, two protocols.

Local (Aider/Ollama): text protocol in system prompt
  TOOL: name(arg=value, ...)

Cloud (OpenAI-compatible): native tools=[] JSON Schema

Dispatcher picks adapter by worker.harness / provider — never mixes formats.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

Protocol = Literal["text", "openai"]


@dataclass(frozen=True)
class ToolParam:
    name: str
    description: str
    type: str = "string"
    required: bool = True


@dataclass
class ToolSpec:
    name: str
    description: str
    params: list[ToolParam] = field(default_factory=list)
    local_safe: bool = True
    cloud_only: bool = False
    write: bool = False


TOOL_CATALOG: list[ToolSpec] = [
    ToolSpec(
        "file_read",
        "Read a source file (utf-8). Prefer relative paths from project root.",
        [ToolParam("path", "File path relative to project root")],
        local_safe=True,
    ),
    ToolSpec(
        "file_write",
        "Write full file content. Prefer shadow *_v2 when policy requires.",
        [
            ToolParam("path", "Target path"),
            ToolParam("content", "Full new file content"),
        ],
        local_safe=True,
        write=True,
    ),
    ToolSpec(
        "search_codebase",
        "Search project sources by regex/plain pattern.",
        [
            ToolParam("query", "Search pattern"),
            ToolParam("path", "Optional subdirectory", required=False),
        ],
        local_safe=True,
    ),
    ToolSpec(
        "run_ast_check",
        "Parse Python file(s) with ast; return syntax errors if any.",
        [ToolParam("path", "File or directory")],
        local_safe=True,
    ),
    ToolSpec(
        "run_tests",
        "Run targeted tests (pytest) for given paths.",
        [ToolParam("paths", "Comma-separated test paths or empty for default", required=False)],
        local_safe=True,
    ),
    ToolSpec("git_status", "Show short git status.", [], local_safe=True),
    ToolSpec(
        "git_diff",
        "Show git diff for optional path.",
        [ToolParam("path", "Optional file path", required=False)],
        local_safe=True,
    ),
]


def tools_for_profile(*, local: bool = True, allow_write: bool = True) -> list[ToolSpec]:
    out: list[ToolSpec] = []
    for t in TOOL_CATALOG:
        if local and not t.local_safe:
            continue
        if local and t.cloud_only:
            continue
        if not allow_write and t.write:
            continue
        out.append(t)
    return out


def to_openai_tools(specs: list[ToolSpec] | None = None) -> list[dict[str, Any]]:
    specs = specs if specs is not None else tools_for_profile(local=False, allow_write=True)
    tools: list[dict[str, Any]] = []
    for t in specs:
        props: dict[str, Any] = {}
        required: list[str] = []
        for p in t.params:
            props[p.name] = {"type": p.type, "description": p.description}
            if p.required:
                required.append(p.name)
        tools.append(
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": {
                        "type": "object",
                        "properties": props,
                        "required": required,
                    },
                },
            }
        )
    return tools


def to_text_protocol(specs: list[ToolSpec] | None = None) -> str:
    specs = specs if specs is not None else tools_for_profile(local=True, allow_write=True)
    lines = [
        "AVAILABLE TOOLS (text protocol — do NOT emit JSON tool calls):",
        "When you need a tool, output a single line:",
        "  TOOL: name(arg1=value1, arg2=value2)",
        "Examples:",
        "  TOOL: file_read(path=src/router.py)",
        "  TOOL: search_codebase(query=def select_executor)",
        "  TOOL: run_ast_check(path=src/bus.py)",
        "",
        "Tool catalog:",
    ]
    for t in specs:
        params = ", ".join(
            f"{p.name}{'?' if not p.required else ''}: {p.description}" for p in t.params
        )
        lines.append(f"- {t.name}({params}) — {t.description}")
    lines.append("Prefer minimal tool use. After TOOL lines, wait for results before editing.")
    return "\n".join(lines)


def adapt_for_worker(worker: Any, *, allow_write: bool | None = None) -> dict[str, Any]:
    harness = str(getattr(worker, "harness", "") or "").lower()
    provider = str(getattr(worker, "provider", "") or "").lower()
    backend = str(getattr(worker, "backend", "") or "").lower()
    # Model profile overrides protocol when present
    try:
        from core.model_profiles import profile_for_worker
        mp = profile_for_worker(worker)
        if not backend:
            backend = str(mp.backend or "").lower()
    except Exception:
        mp = None
    if backend in ("native_tools", "native", "openai_tools", "function_calling"):
        is_local = False
    elif backend in ("aider_cli", "aider", "cli"):
        is_local = True
    else:
        is_local = provider in ("ollama", "local") or harness in ("aider", "cli")
        if harness == "aider":
            is_local = True
    if allow_write is None:
        allow_write = True
    specs = tools_for_profile(local=is_local, allow_write=allow_write)
    if is_local:
        return {
            "protocol": "text",
            "profile": getattr(mp, "name", None) or "local",
            "backend": backend or "aider_cli",
            "tools_openai": None,
            "tools_text": to_text_protocol(specs),
            "tool_names": [t.name for t in specs],
            "context_window": int(getattr(mp, "context_window", 0) or 0),
        }
    return {
        "protocol": "openai",
        "profile": getattr(mp, "name", None) or "cloud",
        "backend": backend or "native_tools",
        "tools_openai": to_openai_tools(specs),
        "tools_text": None,
        "tool_names": [t.name for t in specs],
        "context_window": int(getattr(mp, "context_window", 0) or 0),
    }


def parse_text_tool_line(line: str) -> dict[str, Any] | None:
    import re

    s = (line or "").strip()
    m = re.match(r"^TOOL:\s*([a-zA-Z_][\w]*)\s*(?:\((.*)\))?\s*$", s)
    if not m:
        return None
    name = m.group(1)
    raw_args = (m.group(2) or "").strip()
    args: dict[str, str] = {}
    if raw_args:
        for part in re.split(r",(?![^\"]*\")", raw_args):
            part = part.strip()
            if not part:
                continue
            if "=" in part:
                k, v = part.split("=", 1)
                args[k.strip()] = v.strip().strip("\"'")
            else:
                args["value"] = part.strip("\"'")
    return {"name": name, "args": args}


def execute_via_deterministic(
    name: str,
    args: dict[str, Any],
    *,
    project_root: str | None = None,
) -> dict[str, Any]:
    try:
        from skills.tools import ToolRegistry
    except ImportError:
        from skills.tools import ToolRegistry  # type: ignore

    reg = ToolRegistry(project_root=project_root)
    mapping = {
        "file_read": "read_file",
        "file_write": "write_file",
        "search_codebase": "search_code",
        "run_ast_check": "check_syntax",
        "run_tests": "run_tests",
        "git_status": "git_status",
        "git_diff": "git_diff",
    }
    concrete = mapping.get(name, name)
    if concrete not in reg.tools and name in reg.tools:
        concrete = name
    if concrete not in reg.tools:
        return {"success": False, "error": f"Tool not available: {name}"}
    kwargs = dict(args or {})
    if concrete == "search_code" and "query" in kwargs and "pattern" not in kwargs:
        kwargs["pattern"] = kwargs.pop("query")
    if concrete == "git_diff" and "path" in kwargs and "file" not in kwargs:
        kwargs["file"] = kwargs.pop("path")
    return reg.execute(concrete, **kwargs)


class UnifiedToolGateway:
    def __init__(self, project_root: str | None = None) -> None:
        self.project_root = project_root

    def for_worker(self, worker: Any, *, allow_write: bool = True) -> dict[str, Any]:
        return adapt_for_worker(worker, allow_write=allow_write)

    def inject_text_block(self, message: str, worker: Any, *, allow_write: bool = True) -> str:
        adapted = adapt_for_worker(worker, allow_write=allow_write)
        if adapted["protocol"] != "text" or not adapted.get("tools_text"):
            return message
        if "AVAILABLE TOOLS" in (message or ""):
            return message
        return (message or "").rstrip() + "\n\n" + adapted["tools_text"]

    def openai_tools(self, worker: Any, *, allow_write: bool = True) -> list[dict[str, Any]] | None:
        return adapt_for_worker(worker, allow_write=allow_write).get("tools_openai")
