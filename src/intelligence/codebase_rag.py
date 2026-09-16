# -*- coding: utf-8 -*-
"""Codebase RAG — поиск похожего КОДА в файлах проекта.

ВАЖНО: ищет похожие чанки кода в .py файлах. Для похожих ЗАДАЧ из истории
используется `semantic_memory.py`.

- codebase_rag: файлы проекта → контекст кода
- semantic_memory: история задач → прошлый опыт

Stdlib Jaccard by default; optional sentence_transformers if AGENTBUS_RAG_EMBED=1.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


from utils import tokenize_text_list



def _safe_read_text(path: Path, max_chars: int = 200_000) -> str:
    """Read source with encoding fallbacks — never raise UnicodeDecodeError."""
    raw: bytes
    try:
        raw = path.read_bytes()
    except OSError:
        return ""
    if not raw:
        return ""
    raw = raw[: max_chars * 4]
    for enc in ("utf-8-sig", "utf-8", "cp1251", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")

def _tokenize(text: str) -> list[str]:
    return tokenize_text_list(text)


def _bm25_score(query_tokens: list[str], doc_tokens: list[str], *,
                avgdl: float, df: dict[str, int], n_docs: int,
                k1: float = 1.5, b: float = 0.75) -> float:
    """Okapi BM25 (pure Python, no deps)."""
    if not query_tokens or not doc_tokens or n_docs < 1:
        return 0.0
    from collections import Counter
    import math
    tf = Counter(doc_tokens)
    dl = len(doc_tokens)
    score = 0.0
    for term in set(query_tokens):
        f = tf.get(term, 0)
        if not f:
            continue
        n_qi = df.get(term, 0) or 0
        idf = math.log(1 + (n_docs - n_qi + 0.5) / (n_qi + 0.5))
        denom = f + k1 * (1 - b + b * dl / max(avgdl, 1.0))
        score += idf * (f * (k1 + 1)) / max(denom, 1e-9)
    return float(score)


@dataclass
class Chunk:
    file: str
    start_line: int
    text: str
    tokens: set[str]


class CodebaseRAG:
    """Index .py files by function/class chunks for semantic-ish search."""

    def __init__(self, project_path: str | Path, *, max_files: int = 400) -> None:
        self.root = Path(project_path)
        self.max_files = max_files
        self.chunks: list[Chunk] = []
        self._built_at = 0.0
        self._embed_model = None
        self._index_path = self.root / ".agentbus" / "rag_index.json"
        self._file_mtimes: dict[str, float] = {}

    def _chunk_by_symbols(self, path: Path, content: str) -> list[Chunk]:
        lines = content.splitlines()
        chunks: list[Chunk] = []
        # simple scan for def/class starts
        starts: list[int] = []
        for i, line in enumerate(lines):
            if re.match(r"^(def |class |async def )", line):
                starts.append(i)
        if not starts:
            text = "\n".join(lines[:80])
            toks = set(_tokenize(text))
            if toks:
                chunks.append(Chunk(str(path), 1, text[:2000], toks))
            return chunks
        starts.append(len(lines))
        for a, b in zip(starts, starts[1:]):
            body = "\n".join(lines[a:b])[:2500]
            toks = set(_tokenize(body))
            if len(toks) < 3:
                continue
            rel = str(path)
            try:
                rel = str(path.relative_to(self.root))
            except ValueError:
                pass
            chunks.append(Chunk(rel.replace("\\", "/"), a + 1, body, toks))
        return chunks

    def build_index(self) -> int:
        self.chunks = []
        count = 0
        if not self.root.is_dir():
            return 0
        for py in self.root.rglob("*.py"):
            if any(x in py.parts for x in (".git", "__pycache__", ".venv", "venv", "node_modules", ".agentbus")):
                continue
            try:
                content = _safe_read_text(py)
            except OSError:
                continue
            self.chunks.extend(self._chunk_by_symbols(py, content))
            count += 1
            if count >= self.max_files:
                break
        self._built_at = time.time()
        self._save_index()
        return len(self.chunks)

    def _save_index(self) -> None:
        """Persist chunk metadata to .agentbus/rag_index.json (no embeddings required)."""
        try:
            self._index_path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "built_at": self._built_at,
                "root": str(self.root),
                "chunks": [
                    {
                        "file": c.file,
                        "start_line": c.start_line,
                        "text": c.text[:2500],
                        "tokens": sorted(c.tokens)[:200],
                    }
                    for c in self.chunks[:5000]
                ],
            }
            self._index_path.write_text(
                json.dumps(payload, ensure_ascii=False),
                encoding="utf-8",
            )
        except OSError:
            pass

    def _load_index(self) -> bool:
        if not self._index_path.is_file():
            return False
        try:
            data = json.loads(self._index_path.read_text(encoding="utf-8"))
            chunks = []
            for row in data.get("chunks") or []:
                if not isinstance(row, dict):
                    continue
                toks = set(row.get("tokens") or [])
                chunks.append(
                    Chunk(
                        str(row.get("file") or ""),
                        int(row.get("start_line") or 1),
                        str(row.get("text") or ""),
                        toks,
                    )
                )
            if not chunks:
                return False
            self.chunks = chunks
            self._built_at = float(data.get("built_at") or 0)
            return True
        except Exception:
            return False

    def ensure_index(self, *, max_age_sec: float = 3600.0) -> int:
        """Load disk cache if fresh; else rebuild."""
        if self.chunks and (time.time() - self._built_at) < max_age_sec:
            return len(self.chunks)
        if self._load_index() and (time.time() - self._built_at) < max_age_sec:
            return len(self.chunks)
        return self.build_index()

    def search(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        if not self.chunks:
            self.ensure_index()
        q_list = list(_tokenize(query))
        q = set(q_list)
        if not q:
            return []
        # BM25 corpus stats (token lists from chunk.tokens sets — approximate)
        doc_lists = [list(ch.tokens) for ch in self.chunks]
        n_docs = len(doc_lists) or 1
        avgdl = sum(len(d) for d in doc_lists) / n_docs
        df: dict[str, int] = {}
        for d in doc_lists:
            for term in set(d):
                df[term] = df.get(term, 0) + 1
        use_bm25 = (os.getenv("AGENTBUS_RAG_BM25", "1").strip() not in ("0", "false", "no"))
        scored: list[tuple[float, Chunk]] = []
        for ch, dlist in zip(self.chunks, doc_lists):
            if use_bm25:
                score = _bm25_score(q_list, dlist, avgdl=avgdl, df=df, n_docs=n_docs)
            else:
                inter = len(q & ch.tokens)
                if not inter:
                    continue
                union = len(q | ch.tokens) or 1
                score = inter / union
            # boost filename hits
            if any(t in ch.file.lower() for t in q):
                score += 0.15 if not use_bm25 else score * 0.05 + 0.1
            if score > 0:
                scored.append((score, ch))
        scored.sort(key=lambda x: -x[0])
        out = []
        for score, ch in scored[:top_k]:
            out.append({
                "file": ch.file,
                "line": ch.start_line,
                "score": round(score, 4),
                "preview": ch.text[:400],
            })
        return out

    def as_context(self, query: str, top_k: int = 4, max_chars: int = 3500) -> str:
        hits = self.search(query, top_k=top_k)
        if not hits:
            return ""
        parts = ["CODEBASE RAG:"]
        total = 0
        for h in hits:
            block = f"\n--- {h['file']}:{h['line']} (score={h['score']}) ---\n{h['preview']}"
            if total + len(block) > max_chars:
                break
            parts.append(block)
            total += len(block)
        return "\n".join(parts)


_CACHE: dict[str, CodebaseRAG] = {}


def get_rag(project_path: str | Path, *, rebuild: bool = False) -> CodebaseRAG:
    key = str(Path(project_path).resolve())
    if key not in _CACHE:
        _CACHE[key] = CodebaseRAG(key)
    rag = _CACHE[key]
    if rebuild:
        rag.build_index()
    else:
        rag.ensure_index()
    return rag
