# -*- coding: utf-8 -*-
"""Semantic memory — поиск похожих ЗАДАЧ из истории выполнения.

ВАЖНО: ищет похожие задачи (по тексту сообщения) в истории выполнения.
Для поиска похожего КОДА в файлах проекта — `codebase_rag.py`.

- semantic_memory: история задач → подсказки из прошлого опыта
- codebase_rag: файлы проекта → контекст кода для текущей задачи

Optional: scikit-learn (TF-IDF); иначе Jaccard. Env:
  AGENTBUS_SEMANTIC=1, AGENTBUS_SEMANTIC_MIN_CX=4, AGENTBUS_SEMANTIC_PATH
"""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any


from utils import env_flag, env_int, tokenize_text


def _tokenize(text: str) -> set[str]:
    return tokenize_text(text)


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


class SemanticMemory:
    """Store successful/failed task texts and retrieve similar ones."""

    def __init__(self, memory_path: str | Path | None = None, *, max_entries: int = 500) -> None:
        path = memory_path or os.getenv("AGENTBUS_SEMANTIC_PATH") or "semantic_memory.json"
        self.memory_path = Path(path)
        self.max_entries = max(50, max_entries)
        self.tasks: list[dict[str, Any]] = []
        self._vectorizer = None
        self._vectors = None
        self._load()

    def _load(self) -> None:
        if not self.memory_path.exists():
            return
        try:
            data = json.loads(self.memory_path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                self.tasks = data[-self.max_entries :]
            elif isinstance(data, dict) and isinstance(data.get("tasks"), list):
                self.tasks = data["tasks"][-self.max_entries :]
        except Exception:
            self.tasks = []
        self._rebuild_index()

    def _save(self) -> None:
        try:
            self.memory_path.parent.mkdir(parents=True, exist_ok=True)
            self.memory_path.write_text(
                json.dumps(self.tasks[-self.max_entries :], ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            pass

    def _rebuild_index(self) -> None:
        self._vectorizer = None
        self._vectors = None
        if not self.tasks:
            return
        texts = [str(t.get("message") or "") for t in self.tasks]
        try:
            from sklearn.feature_extraction.text import TfidfVectorizer  # type: ignore

            vec = TfidfVectorizer(lowercase=True, ngram_range=(1, 2), min_df=1)
            self._vectors = vec.fit_transform(texts)
            self._vectorizer = vec
        except Exception:
            self._vectorizer = None
            self._vectors = None

    def add_task(self, task: dict[str, Any]) -> None:
        entry = {
            "message": str(task.get("message") or "")[:2000],
            "files": list(task.get("files") or [])[:20],
            "solution": str(task.get("solution") or task.get("stdout") or "")[:1500],
            "worker": str(task.get("worker") or ""),
            "success": bool(task.get("success", False)),
            "task_type": str(task.get("task_type") or ""),
            "complexity": task.get("complexity"),
            "timestamp": time.time(),
        }
        self.tasks.append(entry)
        if len(self.tasks) > self.max_entries:
            self.tasks = self.tasks[-self.max_entries :]
        self._rebuild_index()
        self._save()

    def find_similar(self, task: dict[str, Any], top_k: int = 5, min_score: float = 0.12) -> list[dict[str, Any]]:
        if not self.tasks:
            return []
        query = str(task.get("message") or "")
        scores: list[tuple[float, int]] = []

        if self._vectorizer is not None and self._vectors is not None:
            try:
                from sklearn.metrics.pairwise import cosine_similarity  # type: ignore
                import numpy as np  # type: ignore

                qv = self._vectorizer.transform([query])
                sims = cosine_similarity(qv, self._vectors)[0]
                for idx, s in enumerate(sims):
                    scores.append((float(s), idx))
            except Exception:
                scores = []

        if not scores:
            qtok = _tokenize(query)
            for idx, t in enumerate(self.tasks):
                s = _jaccard(qtok, _tokenize(str(t.get("message") or "")))
                scores.append((s, idx))

        scores.sort(key=lambda x: -x[0])
        out: list[dict[str, Any]] = []
        for s, idx in scores[: max(1, top_k)]:
            if s < min_score:
                continue
            out.append({"task": self.tasks[idx], "similarity": round(s, 4)})
        return out

    def build_context_from_similar(self, task: dict[str, Any], top_k: int = 3) -> str:
        similar = self.find_similar(task, top_k=top_k)
        if not similar:
            return ""
        lines = ["=== похожие задачи (semantic memory) ==="]
        for item in similar:
            t = item["task"]
            sim = item["similarity"]
            status = "успех" if t.get("success") else "ошибка"
            lines.append(f"- [{status}] sim={sim:.2f} {str(t.get('message') or '')[:160]}")
            sol = str(t.get("solution") or "").strip()
            if sol:
                lines.append(f"  решение: {sol[:220]}")
        return "\n".join(lines)


_GLOBAL: SemanticMemory | None = None


def get_semantic_memory() -> SemanticMemory:
    global _GLOBAL
    if _GLOBAL is None:
        _GLOBAL = SemanticMemory()
    return _GLOBAL


def should_attach_semantic(raw: dict[str, Any] | None = None, complexity: int | None = None) -> bool:
    if not env_flag("AGENTBUS_SEMANTIC"):
        return False
    min_cx = env_int("AGENTBUS_SEMANTIC_MIN_CX", 4)
    if complexity is None and isinstance(raw, dict):
        meta = raw.get("metadata") if isinstance(raw.get("metadata"), dict) else {}
        try:
            complexity = int(raw.get("complexity") if raw.get("complexity") is not None else meta.get("complexity") or 0)
        except (TypeError, ValueError):
            complexity = 0
    try:
        return int(complexity or 0) >= min_cx
    except (TypeError, ValueError):
        return False


if __name__ == "__main__":
    mem = SemanticMemory(memory_path=":memory:")  # path still needed
    mem.memory_path = Path("/tmp/agentbus_sem_test.json")
    mem.tasks = []
    mem.add_task({"message": "разбей длинную функцию process", "success": True, "solution": "extract helpers"})
    mem.add_task({"message": "format imports", "success": True})
    hits = mem.find_similar({"message": "рефакторинг функции process в runtime"}, top_k=2, min_score=0.05)
    print(hits)
    print(mem.build_context_from_similar({"message": "разбей process"}))
