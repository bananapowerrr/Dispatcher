# -*- coding: utf-8 -*-
"""Тесты stream normalizer: detect_kind, normalize_chunk, StreamNormalizer.feed."""
from __future__ import annotations

from eventbus import BUS, AgentEvent, reset_bus
from stream import StreamNormalizer, detect_kind, normalize_chunk, scan_output


def test_detect_kind():
    assert detect_kind("aider: use a tool to read the file") == "tool"
    assert detect_kind("<|tool_use|>") == "tool"
    assert detect_kind("git add src/foo.py") == "tool"
    assert detect_kind("thinking about the approach") == "thinking"
    assert detect_kind("<thinking>") == "thinking"
    assert detect_kind("ordinary output line") == "other"


def test_normalize_chunk_coalesces_same_kind():
    chunk = "plain line\naider: add file.txt\ngit commit -m x\nthinking step 1\nplain2\n"
    evs = normalize_chunk(chunk)
    kinds = [e["kind"] for e in evs]
    assert kinds == ["other", "tool", "thinking", "other"]
    # подряд идущие tool-строки слились в одно событие
    tool = [e for e in evs if e["kind"] == "tool"][0]
    assert "\n" in tool["text"]


def test_normalize_chunk_empty():
    assert normalize_chunk("") == []
    assert normalize_chunk("  \n \n") == []


def test_scan_output():
    txt = "aider: use tool run\n<thinking>a</thinking>\nplain"
    tools, thinks = scan_output(txt)
    assert tools >= 1 and thinks >= 1


def test_stream_normalizer_feed_emits_to_bus():
    bus = reset_bus()
    captured = []
    bus.attach(lambda ev: captured.append(ev))
    n = StreamNormalizer()
    n.feed("aider: add file.txt\ngit commit -m x\nthinking approach\n", task_id="t1",
           worker="w", executor="aider", provider="ollama", model="m")
    types = [ev.type for ev in captured]
    assert "TOOL_CALL" in types
    assert "THINKING" in types
    assert n.count >= 2
    tc = [ev for ev in captured if ev.type == "TOOL_CALL"][0]
    assert tc.task_id == "t1" and tc.worker == "w"
    assert tc.executor == "aider" and tc.provider == "ollama"
    assert tc.model == "m"


def test_stream_normalizer_feed_no_events_plain():
    reset_bus()
    n = StreamNormalizer()
    n.feed("just a normal line\nanother\n")
    assert n.count == 0


def test_stream_normalizer_never_throws_on_bad_emit():
    reset_bus()
    def _bad(kw):
        raise RuntimeError("boom")
    n = StreamNormalizer(emit=_bad)
    # даже при падении emit — feed не бросает, а просто пропускает
    n.feed("aider: add file.txt")
    assert n.count == 0
