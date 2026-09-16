# -*- coding: utf-8 -*-
"""Task grouper — кластеризация ЗАДАЧ между собой по пересечению файлов.

ВАЖНО: группирует несколько задач для пакетной обработки.
Для разбиения ОДНОЙ задачи на подзадачи — `task_decomposer.py`.

- task_grouper: несколько задач → группы по пересечению файлов
- task_decomposer: одна задача → подзадачи по директориям

Pure heuristics, no LLM. Used via GLOBAL_GROUPER.sort_for_processing().
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any

from utils import extract_files


def _task_type(task: dict[str, Any]) -> str:
    """Тип задачи через единый task_classifier."""
    try:
        from skills.task_classifier import classify_task_type
        return classify_task_type(task)
    except ImportError:
        msg = str(task.get("message") or task.get("body") or "").lower()
        if "test" in msg:
            return "test"
        if "fix" in msg or "bug" in msg:
            return "bugfix"
        return "general"


def _project(task: dict[str, Any]) -> str:
    return str(task.get("project") or "").strip() or "_default"


def _files(task: dict[str, Any]) -> set[str]:
    """Множество нормализованных файлов задачи."""
    return set(extract_files(task))


def _file_overlap(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


class TaskGrouper:
    """Group tasks for batch-friendly scheduling."""

    def group(self, tasks: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
        """Group by project:task_type, then merge high file-overlap subgroups."""
        if not tasks:
            return []
        buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for t in tasks:
            key = f"{_project(t)}:{_task_type(t)}"
            buckets[key].append(t)

        groups: list[list[dict[str, Any]]] = []
        for key in sorted(buckets.keys()):
            items = buckets[key]
            groups.extend(self._split_by_overlap(items))
        return groups

    def _split_by_overlap(
        self,
        tasks: list[dict[str, Any]],
        *,
        threshold: float = 0.25,
    ) -> list[list[dict[str, Any]]]:
        """Greedy clustering by Jaccard file overlap."""
        remaining = list(tasks)
        clusters: list[list[dict[str, Any]]] = []
        while remaining:
            seed = remaining.pop(0)
            seed_files = _files(seed)
            cluster = [seed]
            kept: list[dict[str, Any]] = []
            for t in remaining:
                if _file_overlap(seed_files, _files(t)) >= threshold:
                    cluster.append(t)
                    seed_files |= _files(t)
                else:
                    kept.append(t)
            remaining = kept
            clusters.append(cluster)
        return clusters

    def sort_for_processing(self, tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Flatten groups into a processing order."""
        ordered: list[dict[str, Any]] = []
        for group in self.group(tasks):
            # larger file sets first within group (more context reuse potential)
            group_sorted = sorted(
                group,
                key=lambda t: (-len(_files(t)), str(t.get("id") or "")),
            )
            ordered.extend(group_sorted)
        return ordered

    def group_summary(self, tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Debug/metrics view of grouping."""
        out = []
        for i, g in enumerate(self.group(tasks)):
            projects = sorted({_project(t) for t in g})
            types = sorted({_task_type(t) for t in g})
            files: set[str] = set()
            for t in g:
                files |= _files(t)
            out.append({
                "group": i,
                "size": len(g),
                "projects": projects,
                "types": types,
                "files": sorted(files)[:20],
                "ids": [str(t.get("id") or "") for t in g],
            })
        return out


GLOBAL_GROUPER = TaskGrouper()
