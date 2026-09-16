# -*- coding: utf-8 -*-
"""Skill learner — propose new deterministic skills from repeated LLM successes."""
from __future__ import annotations

import json
import os
import re
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


def _store_path() -> Path:
    raw = (os.getenv("AGENTBUS_SKILL_LEARNER") or "").strip()
    if raw:
        return Path(raw)
    try:
        from core.config import BASE_DIR
        return BASE_DIR / ".agentbus" / "skill_observations.json"
    except Exception:
        return Path(".agentbus") / "skill_observations.json"


@dataclass
class SkillCandidate:
    pattern: str
    solution_type: str
    confidence: float
    examples: list[dict[str, Any]] = field(default_factory=list)
    suggested_code: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class SkillLearner:
    """Observe successful tasks and propose skill candidates."""

    PATTERNS: dict[str, str] = {
        "rename_all": r"(?:rename|переимен)\s+(\w+)\s+(?:to|→|->|в)\s+(\w+)",
        "add_logging": r"(?:add|введи|добав)\s+logging",
        "wrap_try": r"(?:wrap|оберни)\s+(?:in\s+)?try",
        "remove_debug": r"(?:remove|убери|удали)\s+(?:print|debug)",
        "sort_imports": r"(?:sort|отсортируй)\s+import",
        "format_code": r"(?:format|отформатируй|black|isort)",
        "strip_whitespace": r"(?:trailing whitespace|хвостовые пробелы|strip whitespace)",
        "bare_except": r"(?:bare except|голый except|except:)",
        "type_hints": r"(?:type hint|typehints|типизац|аннотац)",
        "docstrings": r"(?:docstring|документац\w* к функ)",
        "generate_requirements": r"(?:requirements\.txt|сгенерируй requirements)",
        "normalize_newlines": r"(?:crlf|normalize newlines|переводы строк)",
    }

    def __init__(
        self,
        min_examples: int = 3,
        confidence_threshold: float = 0.7,
        store: Path | None = None,
    ) -> None:
        self.min_examples = min_examples
        self.confidence_threshold = confidence_threshold
        self.store = store or _store_path()
        self.observations: dict[str, list[dict[str, Any]]] = {}
        self._lock = threading.Lock()
        self._load()

    def _load(self) -> None:
        try:
            if self.store.is_file():
                data = json.loads(self.store.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    self.observations = {
                        str(k): list(v) for k, v in data.items() if isinstance(v, list)
                    }
        except Exception:
            self.observations = {}

    def _save(self) -> None:
        try:
            self.store.parent.mkdir(parents=True, exist_ok=True)
            self.store.write_text(
                json.dumps(self.observations, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            pass

    def observe(self, task: dict[str, Any] | Any, result: dict[str, Any] | None = None) -> None:
        """Record a successful resolution (LLM or skill)."""
        try:
            from core.feature_flags import is_enabled
            if not is_enabled("skill_learner", default=True):
                return
        except Exception:
            pass
        result = result or {}
        success = result.get("success", True)
        if success is False:
            return
        if isinstance(task, dict):
            message = str(task.get("message") or "")
            tid = str(task.get("id") or "")
        else:
            message = str(getattr(task, "message", "") or "")
            tid = str(getattr(task, "id", "") or "")
        msg_l = message.lower()
        if not msg_l:
            return
        with self._lock:
            for name, rx in self.PATTERNS.items():
                if re.search(rx, msg_l, re.I):
                    bucket = self.observations.setdefault(name, [])
                    bucket.append(
                        {
                            "id": tid,
                            "message": message[:500],
                            "ts": time.time(),
                            "method": result.get("method") or result.get("worker") or "llm",
                        }
                    )
                    # cap
                    if len(bucket) > 50:
                        self.observations[name] = bucket[-50:]
            self._save()

    def _detect_solution_type(self, examples: list[dict[str, Any]]) -> str:
        methods = [str(e.get("method") or "") for e in examples]
        if any("skill" in m for m in methods):
            return "skill"
        if any("cache" in m for m in methods):
            return "cache"
        return "file_edit"

    def _generate_stub(self, pattern: str) -> str:
        known = {
            "format_code": "Call format_code skill (isort+black).",
            "sort_imports": "Call sort_imports skill.",
            "strip_whitespace": "Call strip_trailing_whitespace skill.",
            "bare_except": "Call find_bare_except report skill.",
            "generate_requirements": "Call generate_requirements skill.",
            "normalize_newlines": "Call normalize_newlines skill.",
        }
        hint = known.get(pattern, f"Implement deterministic handler for {pattern}.")
        return (
            f"# Auto-suggested skill for pattern '{pattern}'\n"
            f"# Hint: {hint}\n"
            f"def skill_{pattern}(root, files=None, **kwargs):\n"
            f"    \"\"\"TODO: wire to existing SkillRegistry or implement.\"\"\"\n"
            f"    return {{'ok': True, 'pattern': '{pattern}'}}\n"
        )

    def find_candidates(self) -> list[SkillCandidate]:
        candidates: list[SkillCandidate] = []
        with self._lock:
            items = list(self.observations.items())
        rejected: set[str] = set()
        try:
            rp = self.store.parent / "skill_rejected.json"
            if rp.is_file():
                rejected = set(json.loads(rp.read_text(encoding="utf-8")) or [])
        except Exception:
            rejected = set()
        for pattern, examples in items:
            if pattern in rejected:
                continue
            if len(examples) < self.min_examples:
                continue
            # confidence: fraction with same method
            methods = [str(e.get("method") or "llm") for e in examples]
            if not methods:
                continue
            top = max(set(methods), key=methods.count)
            similar = sum(1 for m in methods if m == top)
            confidence = similar / len(methods)
            if confidence < self.confidence_threshold:
                continue
            candidates.append(
                SkillCandidate(
                    pattern=pattern,
                    solution_type=self._detect_solution_type(examples),
                    confidence=round(confidence, 3),
                    examples=examples[-3:],
                    suggested_code=self._generate_stub(pattern),
                )
            )
        return sorted(candidates, key=lambda c: -c.confidence)

    def propose_to_user(self, candidate: SkillCandidate) -> dict[str, Any]:
        return {
            "type": "skill_proposal",
            "pattern": candidate.pattern,
            "confidence": candidate.confidence,
            "examples": [e.get("message", "") for e in candidate.examples],
            "suggested_code": candidate.suggested_code,
            "solution_type": candidate.solution_type,
        }

    def stats(self) -> dict[str, Any]:
        with self._lock:
            patterns = {k: len(v) for k, v in sorted(self.observations.items())}
            total = sum(patterns.values())
        # find_candidates takes its own lock — call outside
        return {
            "patterns": patterns,
            "total_observations": total,
            "candidates": len(self.find_candidates()),
        }



    def custom_dir(self) -> Path:
        try:
            from core.config import BASE_DIR
            d = BASE_DIR / "src" / "skills" / "custom"
        except Exception:
            d = Path("src") / "skills" / "custom"
        d.mkdir(parents=True, exist_ok=True)
        init = d / "__init__.py"
        if not init.is_file():
            init.write_text("# auto-generated custom skills\n", encoding="utf-8")
        return d

    def materialize_plugin(self, pattern: str, *, source: str | None = None) -> dict[str, Any]:
        """Validate and write plugin under src/skills/custom/. Does not auto-load into live registry."""
        from safety.skill_sandbox import validate_skill_source
        candidates = {c.pattern: c for c in self.find_candidates()}
        cand = candidates.get(pattern)
        code = source or (cand.suggested_code if cand else self._generate_stub(pattern))
        result = validate_skill_source(code)
        if not result.ok:
            return {"status": "rejected", "validation": result.to_dict()}
        safe = re.sub(r"[^a-zA-Z0-9_]", "_", pattern)[:40]
        path = self.custom_dir() / f"{safe}.py"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(code if code.strip() else self._generate_stub(pattern), encoding="utf-8")
        # re-validate written file
        written = path.read_text(encoding="utf-8")
        v2 = validate_skill_source(written)
        meta = {
            "status": "written" if v2.ok else "written_but_invalid",
            "path": str(path),
            "validation": v2.to_dict(),
            "pattern": pattern,
        }
        try:
            log = self.store.parent / "skill_plugins.json"
            data = []
            if log.is_file():
                data = json.loads(log.read_text(encoding="utf-8")) or []
            data.append({**meta, "ts": time.time()})
            log.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass
        return meta

    def accept(self, pattern: str, *, materialize: bool = False) -> dict[str, Any]:
        """Mark candidate accepted; optionally write validated plugin to skills/custom/."""
        with self._lock:
            path = self.store.parent / "skill_accepted.json"
            accepted: list[str] = []
            try:
                if path.is_file():
                    raw = json.loads(path.read_text(encoding="utf-8")) or []
                    accepted = [x if isinstance(x, str) else str(x.get("pattern") or x) for x in raw]
            except Exception:
                accepted = []
            if pattern not in accepted:
                accepted.append(pattern)
            try:
                path.write_text(json.dumps(accepted, ensure_ascii=False, indent=2), encoding="utf-8")
            except Exception:
                pass
        out: dict[str, Any] = {"accepted": pattern, "status": "ok"}
        if materialize:
            out["plugin"] = self.materialize_plugin(pattern)
        return out

    def reject(self, pattern: str) -> dict[str, Any]:
        """Drop observations for pattern so it stops proposing."""
        with self._lock:
            self.observations.pop(pattern, None)
            self._save()
            path = self.store.parent / "skill_rejected.json"
            rejected: list[str] = []
            try:
                if path.is_file():
                    rejected = list(json.loads(path.read_text(encoding="utf-8")) or [])
            except Exception:
                rejected = []
            if pattern not in rejected:
                rejected.append(pattern)
            try:
                path.write_text(json.dumps(rejected, ensure_ascii=False, indent=2), encoding="utf-8")
            except Exception:
                pass
        return {"rejected": pattern, "status": "ok"}



GLOBAL_SKILL_LEARNER = SkillLearner()
