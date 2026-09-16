# -*- coding: utf-8 -*-
from context_budget import assemble_worker_message, estimate_tokens, compress_to_bullets
from structured_output import parse_json, repair_prompt, extract_json_text


def test_assemble_keeps_user_request():
    body = assemble_worker_message(
        user_request="fix task",
        memory="PROJECT MEMORY:\n- use pytest",
        conversation="CONVERSATION:\n" + ("old line\n" * 200),
        rag="CODEBASE RAG:\n" + ("def x():\n  pass\n" * 80),
        total_chars=2500,
    )
    assert "USER REQUEST" in body
    assert "USER REQUEST" in body and "test" in body
    assert len(body) <= 2800


def test_estimate_tokens_positive():
    assert estimate_tokens("hello world") > 0


def test_parse_json_fence():
    v, err = parse_json('Sure:\n```json\n{"ok": true, "n": 1}\n```')
    assert err is None
    assert v == {"ok": True, "n": 1}


def test_parse_json_trailing_comma():
    v, err = parse_json('{"a": 1,}')
    assert err is None
    assert v == {"a": 1}


def test_repair_prompt_mentions_error():
    p = repair_prompt("Return JSON", "not json", "no JSON found")
    assert "валидн" in p.lower() or "JSON" in p
