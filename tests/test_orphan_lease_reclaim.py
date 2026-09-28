# -*- coding: utf-8 -*-
"""Регрессия: reclaim_stuck обязан убирать осиротевшие lease-файлы.

Найдено на аудите 2026-09-29: в channels/desktop/processing/ лежал
plan-1-s1.lease.json без соответствующего task-JSON (задача уже ушла в
errors/). Цикл в reclaim_stuck делал `continue` по .lease.json, поэтому
такой файл не видел никогда и висел бесконечно. Он же:
  * путал status_board / панели, считающие файлы в processing/;
  * рисковал блокировать повторный claim задачи.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from core.reclaim import reclaim_stuck, write_lease


def _dirs(tmp_path: Path) -> tuple[Path, Path, Path]:
    proc = tmp_path / "processing"
    inc = tmp_path / "incoming"
    err = tmp_path / "errors"
    for d in (proc, inc, err):
        d.mkdir(parents=True, exist_ok=True)
    return proc, inc, err


def test_orphan_lease_removed(tmp_path: Path) -> None:
    """Lease без task-JSON удаляется."""
    proc, inc, err = _dirs(tmp_path)
    write_lease(proc / "ghost.json", task_id="ghost")   # создаст ghost.lease.json
    lease = proc / "ghost.lease.json"
    assert lease.is_file()

    results = reclaim_stuck(processing_dir=proc, incoming_dir=inc, errors_dir=err)

    assert not lease.is_file(), "осиротевший lease остался в processing/"
    assert any(r.get("action") == "LEASE_REMOVED" for r in results)
    assert any(r.get("id") == "ghost" for r in results)


def test_lease_with_task_is_kept(tmp_path: Path) -> None:
    """Живой lease не трогаем: основной проход им займётся."""
    proc, inc, err = _dirs(tmp_path)
    task = proc / "live.json"
    task.write_text(json.dumps({
        "id": "live", "attempts": 0, "status": "PROCESSING",
    }), encoding="utf-8")
    write_lease(task, task_id="live")
    lease = proc / "live.lease.json"
    assert lease.is_file()

    reclaim_stuck(processing_dir=proc, incoming_dir=inc, errors_dir=err)

    assert lease.is_file(), "lease при живом task-JSON не должен удаляться"


def test_orphan_cleanup_does_not_break_requeue(tmp_path: Path) -> None:
    """Сирота чистится, а реально зависшая задача всё равно requeue-ится."""
    proc, inc, err = _dirs(tmp_path)
    # сирота: lease без task-JSON
    write_lease(proc / "ghost.json", task_id="ghost")
    # зависшая задача: старый heartbeat и в JSON, и в mtime
    old = 1.0
    task = proc / "stuck.json"
    task.write_text(json.dumps({
        "id": "stuck", "attempts": 0, "status": "PROCESSING",
        "metadata": {"last_heartbeat": old},
    }), encoding="utf-8")
    lease = proc / "stuck.lease.json"
    lease.write_text(json.dumps({
        "task_id": "stuck", "attempts": 0, "last_heartbeat": old,
        "stuck_timeout_sec": 60.0, "phase": "process",
    }), encoding="utf-8")
    os.utime(task, (old, old))
    os.utime(lease, (old, old))

    results = reclaim_stuck(processing_dir=proc, incoming_dir=inc, errors_dir=err,
                            base_sec=60, max_sec=60, now=old + 3600)

    assert not (proc / "ghost.lease.json").is_file(), "сирота не убрана"
    requeued = [r for r in results
                if r.get("action") == "REQUEUE"
                and str(r.get("file") or r.get("id") or "") == "stuck.json"]
    assert requeued, f"stuck не requeue-нут: {results}"
    # requeue переносит задачу в incoming; lease уходит вместе с ней,
    # поэтому processing/ должен остаться без хвостов.
    assert (inc / "stuck.json").is_file(), "задача не переехала в incoming"
    assert not list(proc.glob("*.lease.json")), "в processing остался lease"
