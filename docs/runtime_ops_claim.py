# -*- coding: utf-8 -*-
"""RuntimeOpsClaim — file-bus claim, lease, deferred, retry scheduling."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from .bus import FileBus
from .config import (
    CHANNELS, DEFAULT_CHANNEL, MAX_ATTEMPTS, RETRY_DELAY_SECONDS, LEASE_SECONDS,
)
from .tasks import Task

try:
    from core.feature_flags import is_enabled
except Exception:  # pragma: no cover
    def is_enabled(name: str, default: bool = True) -> bool:
        return default


class RuntimeOpsClaim:
    """Mixin: channel claim / recover / deferred / retry queue."""

    def _active_channels(self) -> list[str]:
        """Configured CHANNELS plus on-disk isolated sub-agent channels (*__sub_*)."""
        found: list[str] = []
        seen: set[str] = set()
        for ch in CHANNELS:
            if ch and ch not in seen:
                found.append(ch)
                seen.add(ch)
        try:
            bus_root = Path(getattr(self.bus, "root", None) or "")
            root = bus_root / "channels" if bus_root.is_dir() else Path()
            if not root.is_dir():
                from core.config import CHANNELS_ROOT
                root = Path(CHANNELS_ROOT)
            if root.is_dir():
                for d in sorted(root.iterdir()):
                    if not d.is_dir():
                        continue
                    name = d.name
                    if name in seen:
                        continue
                    # isolated children: gpt__sub_xxx or any configured prefix
                    if "__sub_" in name:
                        found.append(name)
                        seen.add(name)
                        continue
                    # also pick up channels that have pending work even if not in env list
                    if (d / "incoming").is_dir() or (d / "processing").is_dir():
                        # only auto-add __sub_ to avoid scanning random dirs; base channels from env
                        pass
        except Exception:
            pass
        return found

    def _claim_file_task(self) -> dict | None:
        """Claim next incoming task; prefer grouper order (project/type/files)."""
        candidates: list[tuple[object, dict, str]] = []
        for channel in self._active_channels():
            incoming = self.bus.paths(channel)["incoming"]
            for path in sorted(incoming.glob("*.json"), key=lambda p: p.stat().st_mtime):
                try:
                    raw = json.loads(path.read_text(encoding="utf-8"))
                    if not isinstance(raw, dict):
                        continue
                    raw = dict(raw)
                    raw.setdefault("channel", channel)
                    candidates.append((path, raw, channel))
                except (OSError, json.JSONDecodeError, ValueError) as exc:
                    self.log.write(f"битая задача {path.name}: {exc}")
                    try:
                        self.bus.move(channel, "incoming", "errors", path.name)
                    except Exception:
                        pass
        if not candidates:
            return None
        try:
            from skills.task_grouper import GLOBAL_GROUPER
            ordered_raw = GLOBAL_GROUPER.sort_for_processing([c[1] for c in candidates])
            # map back to paths by id/message
            by_id = {}
            for path, raw, channel in candidates:
                key = str(raw.get("id") or "") or id(raw)
                by_id[key] = (path, raw, channel)
            ordered: list[tuple[object, dict, str]] = []
            used = set()
            for raw in ordered_raw:
                key = str(raw.get("id") or "")
                item = by_id.get(key)
                if item and key not in used:
                    ordered.append(item)
                    used.add(key)
            for path, raw, channel in candidates:
                key = str(raw.get("id") or "") or id(raw)
                if key not in used:
                    ordered.append((path, raw, channel))
        except Exception:
            ordered = candidates

        for path, raw, channel in ordered:
            try:
                task = Task.from_dict(raw)
                task.id = str(task.id or uuid.uuid4())
                task.channel = channel
                try:
                    from core.capability_router import enrich_task_from_plugins, infer_capabilities
                    if not isinstance(task.metadata, dict):
                        task.metadata = {}
                    task.metadata = enrich_task_from_plugins(
                        task.message or "", task.metadata
                    )
                    caps = infer_capabilities(task)
                    if caps:
                        task.metadata.setdefault("capabilities", caps)
                except Exception:
                    pass
                if not self.bus.move(channel, "incoming", "processing", path.name):
                    continue
                try:
                    from core.reclaim import write_lease, compute_stuck_timeout_sec, task_complexity
                    proc = self.bus.paths(channel)["processing"] / path.name
                    td = task.to_dict()
                    write_lease(
                        proc,
                        task_id=str(task.id),
                        worker=str(task.worker or task.executor or ""),
                        complexity=task_complexity(td),
                        attempts=int(task.attempts or 0),
                        stuck_timeout_sec=compute_stuck_timeout_sec(td),
                        phase="claim",
                    )
                except Exception:
                    pass
                return task.to_dict()
            except (OSError, ValueError) as exc:
                self.log.write(f"claim {getattr(path, 'name', path)}: {exc}")
                continue
        return None

    def _recover_stale_processing(self, stale_seconds: int = LEASE_SECONDS) -> int:
        """Reclaim stuck processing tasks with adaptive timeout (complexity/worker).

        Uses core.reclaim when available; falls back to fixed mtime lease.
        Returns number of successfully moved tasks.
        """
        try:
            from core.reclaim import reclaim_stuck
            from core.config import STUCK_BASE_SEC, STUCK_TIMEOUT_MAX, MAX_ATTEMPTS as _MAX_ATT
        except Exception:
            recovered = 0
            for channel in self._active_channels():
                pdir = self.bus.paths(channel)["processing"]
                now = time.time()
                for path in pdir.glob("*.json"):
                    if path.name.endswith(".lease.json"):
                        continue
                    try:
                        if now - path.stat().st_mtime <= stale_seconds:
                            continue
                        if self.bus.move(channel, "processing", "incoming", path.name):
                            recovered += 1
                    except OSError:
                        continue
            return recovered

        recovered = 0
        base = float(STUCK_BASE_SEC)
        # floor: never stricter than caller stale_seconds for simple tasks
        base = max(base, min(float(stale_seconds), base * 2))
        for channel in self._active_channels():
            paths = self.bus.paths(channel)
            try:
                results = reclaim_stuck(
                    processing_dir=paths["processing"],
                    incoming_dir=paths["incoming"],
                    errors_dir=paths["errors"],
                    channel=channel,
                    bus_move=self.bus.move,
                    max_attempts=int(_MAX_ATT),
                    base_sec=base,
                    max_sec=float(STUCK_TIMEOUT_MAX),
                )
            except Exception as exc:
                self.log.write(f"reclaim {channel}: {exc}")
                continue
            for item in results:
                if item.get("moved"):
                    recovered += 1
                    self.log.write(
                        f"RECLAIM {item.get('action')} {item.get('file')} "
                        f"age={item.get('age_sec')}s timeout={item.get('timeout_sec')}s "
                        f"attempts={item.get('attempts')}"
                    )
                    try:
                        self._emit(
                            "RECLAIM",
                            f"{item.get('action')} · {item.get('file')}",
                            task_id=str(item.get("file") or "").replace(".json", ""),
                            worker=self.worker_id,
                            payload=item,
                        )
                    except Exception:
                        pass
        return recovered

    def _touch_task_lease(self, task: "Task", phase: str = "work") -> None:
        """Refresh processing lease heartbeat for long-running tasks."""
        try:
            from core.reclaim import touch_lease, write_lease, compute_stuck_timeout_sec, task_complexity
            p = self.bus.paths(task.channel)["processing"] / f"{task.id}.json"
            if not p.is_file():
                return
            lease = p.with_name(p.stem + ".lease.json")
            if not lease.is_file():
                write_lease(
                    p,
                    task_id=str(task.id),
                    worker=str(getattr(task, "worker", "") or ""),
                    complexity=task_complexity(task.to_dict()),
                    attempts=int(getattr(task, "attempts", 0) or 0),
                    stuck_timeout_sec=compute_stuck_timeout_sec(task.to_dict()),
                    phase=phase,
                )
            else:
                touch_lease(p, phase=phase)
            try:
                p.touch()
            except OSError:
                pass
        except Exception:
            pass

    def _recover_deferred(self) -> int:
        recovered = 0
        now = time.time()
        for channel in self._active_channels():
            ddir = self.bus.paths(channel)["deferred"]
            for path in list(ddir.glob("*.json")):
                try:
                    raw = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError, ValueError):
                    continue
                result = raw.get("result") if isinstance(raw, dict) else None
                if not isinstance(result, dict):
                    result = {}
                wake_epoch = result.get("wake_epoch")
                due = False
                if isinstance(wake_epoch, (int, float)) and wake_epoch > 0:
                    due = now >= float(wake_epoch)
                else:
                    try:
                        due = (now - path.stat().st_mtime) >= RETRY_DELAY_SECONDS
                    except OSError:
                        continue
                if not due:
                    continue
                if self.bus.move(channel, "deferred", "incoming", path.name):
                    recovered += 1
                    tid = (raw.get("id") if isinstance(raw, dict) else None) or path.stem
                    self._emit("RETRY", f"deferred→incoming · {tid}",
                               task_id=str(tid), worker=self.worker_id,
                               payload={"from": "deferred"})
        return recovered

    def _schedule_retry(self, task: Task, error: str) -> None:
        self._backoff[task.id] = time.monotonic() + RETRY_DELAY_SECONDS
        task.metadata["prev_failure"] = (error or "")[-2000:]
        try:
            self.queue.bump_attempts(task.id, task.attempts, error)
        except Exception as exc:
            self.log.write(f"bump_attempts: {exc}")

    def _flush_backoff(self) -> None:
        now = time.monotonic()
        due = [tid for tid, when in self._backoff.items() if now >= when]
        for tid in due:
            del self._backoff[tid]
            try:
                self.queue.release(tid, error="повтор после backoff")
            except Exception as exc:
                self.log.write(f"release backoff: {exc}")
        try:
            n = self._recover_deferred()
            if n:
                self.log.write(f"deferred→incoming: {n}")
        except Exception as exc:
            self.log.write(f"recover_deferred: {exc}")

    def _deferred_capacity(self, task: Task, complexity: int) -> bool:
        try:
            snap = self.capacity.deferred_snapshot()
            if not snap.get("deferred"):
                return False
        except Exception:
            return False
        delay = int(snap.get("wake_at") or 60)
        if delay > 86400:
            delay = min(3600, max(60, delay % 86400 or 60))
        delay = max(30, min(delay, 3600))
        wake_epoch = time.time() + delay
        self._emit("DEFERRED_QUOTA", f"пул недоступен, повтор ~{delay}с",
                   task_id=task.id, worker=self.worker_id,
                   payload={"wake_at": delay, "wake_epoch": wake_epoch})
        self._backoff[task.id] = time.monotonic() + delay
        self.bus.move(task.channel, "processing", "deferred", f"{task.id}.json")
        self._save(task, "deferred", {
            "error": "DEFERRED_QUOTA", "attempts": task.attempts,
            "category": "RATE_LIMIT", "wake_at": delay, "wake_epoch": wake_epoch,
        })
        return True


