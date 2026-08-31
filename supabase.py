# -*- coding: utf-8 -*-
"""Очередь AgentBus через RPC Supabase."""
from __future__ import annotations
import json
import urllib.error
import urllib.request
from typing import Any
from config import SUPABASE_KEY, SUPABASE_URL

class SupabaseQueue:
    def __init__(self, url: str = SUPABASE_URL, key: str = SUPABASE_KEY):
        self.url, self.key = url.rstrip("/"), key

    def _request(self, method: str, path: str, payload: Any = None, query: str = "") -> Any:
        if not self.url or not self.key:
            raise RuntimeError("Supabase не настроен")
        body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(f"{self.url}/rest/v1/{path}{query}", data=body, method=method, headers={
            "apikey": self.key, "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json", "Accept": "application/json",
        })
        try:
            with urllib.request.urlopen(req, timeout=15) as response:
                raw = response.read().decode("utf-8")
                return json.loads(raw) if raw else []
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Supabase HTTP {exc.code}: {detail[:2000]}") from exc

    def claim(self, worker_id: str) -> dict[str, Any] | None:
        rows = self._request("POST", "rpc/agentbus_claim_task", {"worker_id": worker_id})
        return (rows[0] if isinstance(rows, list) else rows) if rows else None

    def finish(self, task_id: str, worker_id: str, status: str, result: str = "", error: str = "") -> Any:
        return self._request("POST", "rpc/agentbus_finish_task", {
            "task_id": str(task_id), "worker_id": worker_id, "status": status,
            "result": result[-10000:], "error": error[-10000:],
        })

    def requeue(self, task_id: str, error: str) -> Any:
        return self._request("PATCH", "agentbus_tasks", {
            "status": "PENDING", "error": error[-10000:],
        }, f"?id=eq.{task_id}&status=eq.CLAIMED")

    def release(self, task_id: str, error: str, attempts: int | None = None) -> Any:
        """Свой scheduler: вернуть CLAIMED-задачу в PENDING для повторной попытки
        после backoff (полностью под контролем диспетчера)."""
        payload: dict[str, Any] = {"status": "PENDING", "error": error[-10000:]}
        if attempts is not None:
            payload["attempts"] = int(attempts)
        return self._request("PATCH", "agentbus_tasks", payload,
                             f"?id=eq.{task_id}&status=eq.CLAIMED")

    def bump_attempts(self, task_id: str, attempts: int, error: str) -> Any:
        return self._request("PATCH", "agentbus_tasks", {
            "attempts": int(attempts), "error": error[-10000:],
        }, f"?id=eq.{task_id}")

    def terminal(self, task_id: str, status: str, error: str = "", result: str = "",
                 attempts: int | None = None) -> Any:
        """Финальный статус (DONE/ERROR/BLOCKED) для задачи."""
        payload: dict[str, Any] = {"status": status, "error": error[-10000:],
                                   "result": (result or "")[-10000:]}
        if attempts is not None:
            payload["attempts"] = int(attempts)
        return self._request("PATCH", "agentbus_tasks", payload, f"?id=eq.{task_id}")

    def recover_stale_claimed(self, stale_seconds: int, max_attempts: int) -> tuple[int, int]:
        """Стартовый sweep: (возвращено в PENDING, завершено ERROR).
        Задачи, зависшие в CLAIMED дольше lease, возвращаем на ретрай; те, что
        превысили max_attempts — завершаем ERROR (чинит «горячий цикл» и зависшие
        задачи вроде 3221d46b)."""
        rereleased = errored = 0
        try:
            rows = self._request("GET", "agentbus_tasks",
                                 query="?status=eq.CLAIMED&select=id,attempts,claimed_by,error&limit=1000")
        except Exception:
            return 0, 0
        if not isinstance(rows, list):
            return 0, 0
        import time as _t
        now = _t.time()
        for row in rows:
            tid = row.get("id")
            if not tid:
                continue
            attempts = int(row.get("attempts") or 0)
            claimed_at = row.get("claimed_at")
            stale = self._is_stale(claimed_at, now, stale_seconds)
            if not stale and attempts < max_attempts:
                continue
            if attempts >= max_attempts:
                try:
                    self.terminal(tid, "ERROR", error=(row.get("error") or "превышен лимит попыток"))
                    errored += 1
                except Exception:
                    pass
            else:  # stale, attempts < max
                try:
                    self.release(tid, error=(row.get("error") or "разблокировка зависшего lease"))
                    rereleased += 1
                except Exception:
                    pass
        return rereleased, errored

    @staticmethod
    def _is_stale(claimed_at: Any, now: float, stale_seconds: int) -> bool:
        if not claimed_at:
            return True
        try:
            from datetime import datetime, timezone
            ts = datetime.fromisoformat(str(claimed_at).replace("Z", "+00:00"))
            return (now - ts.timestamp()) > stale_seconds
        except Exception:
            return True

    def requeue_stale(self, stale_seconds: int, max_attempts: int) -> Any:
        return self._request("POST", "rpc/agentbus_requeue_stale", {
            "stale_seconds": stale_seconds, "max_attempts": max_attempts,
        })
