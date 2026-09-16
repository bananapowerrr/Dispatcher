# -*- coding: utf-8 -*-
from __future__ import annotations

from workers import Worker
from tool_registry import (
    adapt_for_worker,
    to_openai_tools,
    to_text_protocol,
    parse_text_tool_line,
    execute_via_deterministic,
    UnifiedToolGateway,
)


def test_openai_schema_shape():
    tools = to_openai_tools()
    assert tools
    assert tools[0]["type"] == "function"
    assert "name" in tools[0]["function"]
    assert "parameters" in tools[0]["function"]


def test_text_protocol_contains_catalog():
    text = to_text_protocol()
    assert "TOOL:" in text
    assert "file_read" in text
    assert "search_codebase" in text


def test_adapt_local_vs_cloud():
    local = Worker(name="aider_local", command=("aider",), harness="aider", provider="ollama", tier=5)
    cloud = Worker(name="sf", command=("x",), harness="opencode", provider="siliconflow", tier=9)
    a = adapt_for_worker(local)
    b = adapt_for_worker(cloud)
    assert a["protocol"] == "text"
    assert a["tools_text"]
    assert b["protocol"] == "openai"
    assert b["tools_openai"]


def test_parse_tool_line():
    p = parse_text_tool_line('TOOL: file_read(path=src/a.py)')
    assert p is not None
    assert p["name"] == "file_read"
    assert p["args"]["path"] == "src/a.py"
    assert parse_text_tool_line("hello") is None


def test_execute_read(tmp_path):
    f = tmp_path / "x.py"
    f.write_text("x = 1\n", encoding="utf-8")
    res = execute_via_deterministic("file_read", {"path": str(f)}, project_root=str(tmp_path))
    assert res.get("success")
    assert "x = 1" in str(res.get("result") or "")


def test_gateway_inject():
    local = Worker(name="l", command=("a",), harness="aider", provider="ollama")
    gw = UnifiedToolGateway()
    msg = gw.inject_text_block("TASK:\nfix me", local)
    assert "AVAILABLE TOOLS" in msg
    assert "file_read" in msg
