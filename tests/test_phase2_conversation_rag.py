# -*- coding: utf-8 -*-
from pathlib import Path
from conversation import Conversation
from session_memory import SessionMemory
from codebase_rag import CodebaseRAG


def test_compact_preserves_pending_and_summarizes():
    c = Conversation(session_id="s1", project="p")
    for i in range(10):
        c.add_message("user", f"u{i} file{i}.py fixed", task_id=f"t{i}")
        c.add_message("assistant", f"a{i}", task_id=f"t{i}")
    c.add_message("user", "still open", task_id="open1")
    msg = c.compact(keep_last=3, use_llm=True)
    assert "compact" in msg.lower() or "already" in msg.lower()
    assert any(m.task_id == "open1" for m in c.messages)
    assert any(m.role == "system" for m in c.messages) or len(c.messages) <= 6


def test_export_and_clear():
    c = Conversation(session_id="s2")
    c.add_message("user", "hello")
    c.add_message("assistant", "hi")
    md = c.export_markdown()
    assert "HELLO" in md.upper() or "USER" in md
    n = c.clear(keep_system=False)
    assert n >= 2
    assert c.messages == []


def test_session_memory_dedupe_and_extract(tmp_path: Path):
    sm = SessionMemory(tmp_path)
    sm.add("uses pytest")
    sm.add("uses pytest")
    assert sm.load().count("pytest") == 1
    sm.auto_extract({"message": "prefer logging", "files": []}, {"success": True})
    assert "logging" in sm.load().lower()


def test_rag_disk_cache(tmp_path: Path):
    (tmp_path / "a.py").write_text("def foo():\n    return 1\n", encoding="utf-8")
    rag = CodebaseRAG(tmp_path)
    n = rag.build_index()
    assert n >= 1
    assert rag._index_path.is_file()
    rag2 = CodebaseRAG(tmp_path)
    assert rag2._load_index()
    hits = rag2.search("foo")
    assert hits and hits[0]["score"] > 0
