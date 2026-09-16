# -*- coding: utf-8 -*-
"""Идемпотентность задач AgentBus.

Формирует стабильный SHA-256 по смысловым полям задачи и хранит уже
запущенные fingerprints на диске. Служебные поля (id, status, attempts,
worker) намеренно не участвуют в fingerprint.
"""
from __future__ import annotations
import hashlib
import json
import threading
from pathlib import Path
from typing import Any

DEFAULT_STATE_FILE = Path(".agentbus") / "dedupe.json"


# Metadata keys that must NOT affect identity (runtime noise / lease / reclaim).
_EXCLUDE_META = frozenset({
    "updated_at",
    "updated_at_epoch",
    "prev_failure",
    "claimed_by",
    "claimed_at",
    "last_heartbeat",
    "reclaim_reason",
    "reclaim_age_sec",
    "reclaim_timeout_sec",
    "attempts",
    "retries",
    "worker",
    "phase",
    "last_explanation",
    "queued",
    "created_at",
    "session_id",
    "fingerprint",  # self-reference if stored
})


def normalize_message(message: str) -> str:
    """Collapse whitespace so trivial reformatting does not change identity."""
    return " ".join(str(message or "").split())


def task_fingerprint(task: Any) -> str:
    """Official AgentBus task identity (SHA-256 hex).

    Used by: dedupe, cache correlation, metrics, UI audit.
    Excludes id/status/attempts/worker and volatile metadata.
    """
    if hasattr(task, "to_dict"):
        data = task.to_dict()
    elif isinstance(task, dict):
        data = dict(task)
    else:
        raise TypeError("task must be a Task or dict")
    meta_in = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
    meta = {
        str(k): v
        for k, v in meta_in.items()
        if str(k) not in _EXCLUDE_META and not str(k).startswith("_")
    }
    canonical = {
        "project": str(data.get("project") or "").strip(),
        "message": normalize_message(str(data.get("message") or "")),
        "files": sorted(str(x).replace("\\", "/").strip() for x in (data.get("files") or []) if str(x).strip()),
        "verify": [str(x).strip() for x in (data.get("verify") or []) if str(x).strip()],
        "run": [str(x).strip() for x in (data.get("run") or []) if str(x).strip()],
        "executor": str(data.get("executor") or "").strip(),
        "channel": str(data.get("channel") or "").strip(),
        "metadata": meta,
    }
    payload = json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class DedupeRegistry:
    def __init__(self, state_file: str | Path = DEFAULT_STATE_FILE):
        self.state_file = Path(state_file)
        self._lock = threading.Lock()
        self._seen: dict[str, dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        try:
            raw = json.loads(self.state_file.read_text(encoding="utf-8"))
            self._seen = raw if isinstance(raw, dict) else {}
        except (OSError, ValueError):
            self._seen = {}

    def _save(self) -> None:
        try:
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.state_file.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(self._seen, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(self.state_file)
        except OSError:
            pass

    def contains(self, fingerprint: str) -> bool:
        with self._lock:
            return fingerprint in self._seen

    def mark(self, fingerprint: str, task_id: str = "") -> None:
        with self._lock:
            self._seen[fingerprint] = {"task_id": str(task_id or "")}
            self._save()

    def check_and_mark(self, fingerprint: str, task_id: str = "") -> bool:
        """True = новый fingerprint и он теперь зарезервирован; False = дубль."""
        with self._lock:
            if fingerprint in self._seen:
                return False
            self._seen[fingerprint] = {"task_id": str(task_id or "")}
            self._save()
            return True

    def forget(self, fingerprint: str) -> None:
        with self._lock:
            self._seen.pop(fingerprint, None)
            self._save()

    def snapshot(self) -> dict[str, dict[str, Any]]:
        with self._lock:
            return dict(self._seen)
