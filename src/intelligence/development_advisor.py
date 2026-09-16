# -*- coding: utf-8 -*-
"""FC-37B Development Advisor — human-readable next steps from analysis.

Builds on quick_scan (37A). No LLM. Does not mutate LivingPlan unless
caller explicitly applies a confirmed draft.
"""
from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from intelligence.project_analysis import (
    AnalysisReport,
    Opportunity,
    opportunities_as_plan_hints,
    quick_scan,
)


@dataclass
class Advice:
    """One recommended next move for the user."""

    rank: int
    title: str
    why: str
    category: str
    priority: int
    opportunity_id: str = ""
    suggested_action: str = ""  # text for a plan step

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AdvisorReport:
    """Product-facing advice package."""

    headline: str = ""
    situation: str = ""
    advice: list[Advice] = field(default_factory=list)
    risks_note: str = ""
    blockers_note: str = ""
    analysis: dict[str, Any] = field(default_factory=dict)
    plan_draft: list[dict[str, Any]] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["advice"] = [a.to_dict() if isinstance(a, Advice) else a for a in self.advice]
        return d

    def format_human(self) -> str:
        lines = [
            "=== Что сейчас происходит ===",
            self.situation or self.headline or "—",
            "",
            "=== Я бы продолжил с этого ===",
        ]
        if not self.advice:
            lines.append("  (явных следующих шагов нет — проект выглядит базово укомплектованным)")
        for a in self.advice:
            lines.append(f"  {a.rank}. {a.title}")
            if a.why:
                lines.append(f"     Почему: {a.why}")
        if self.risks_note:
            lines.extend(["", "=== Риски ===", self.risks_note])
        if self.blockers_note:
            lines.extend(["", "=== Нужно ваше решение ===", self.blockers_note])
        lines.extend([
            "",
            "Можно: [Добавить в план] выбранные пункты или [Пусть Supervisor выберет].",
        ])
        return "\n".join(lines)


_WHY = {
    "init_git": "Без git агент не сможет безопасно откатывать изменения.",
    "add_tests": "Без тестов verification ladder не отличит хороший патч от поломки.",
    "more_tests": "Мало тестов относительно размера кода — высокий риск false-DONE.",
    "deps_manifest": "Иначе окружение на другой машине не воспроизводится.",
    "add_readme": "Новому человеку (и будущему вам) нужен понятный вход в проект.",
    "add_ci": "Автопроверка ловит регрессии до того, как они доедут до прод/ночного прогона.",
    "clear_todos": "Накопившиеся TODO часто указывают на недоделанные инварианты.",
}


def _situation_text(report: AnalysisReport) -> str:
    parts = [
        f"Проект похож на «{report.kind}»: {report.py_files} Python-файлов",
    ]
    if report.test_files:
        parts.append(f"тестов: {report.test_files}")
    else:
        parts.append("тестов не видно")
    markers = []
    if report.has_git:
        markers.append("git")
    if report.has_readme:
        markers.append("README")
    if report.has_pyproject:
        markers.append("pyproject")
    if report.has_ci:
        markers.append("CI")
    if markers:
        parts.append("есть " + ", ".join(markers))
    else:
        parts.append("базовых маркеров почти нет")
    if report.entrypoints:
        parts.append("вход: " + ", ".join(report.entrypoints[:4]))
    return ". ".join(parts) + "."


def _advice_from_opportunity(rank: int, op: Opportunity) -> Advice:
    why = _WHY.get(op.id) or op.detail or f"Категория: {op.category}"
    return Advice(
        rank=rank,
        title=op.title,
        why=why,
        category=op.category,
        priority=op.priority,
        opportunity_id=op.id,
        suggested_action=op.title,
    )


def advise(
    project_root: str | Path | None = None,
    *,
    report: AnalysisReport | None = None,
    state: Any | None = None,
    limit: int = 3,
    use_index: bool = False,
) -> AdvisorReport:
    """Build advisor report from path or existing AnalysisReport."""
    if report is None:
        if project_root is None:
            raise ValueError("project_root or report required")
        report = quick_scan(project_root, state=state, use_index=use_index)

    top = report.top_actions(limit)
    advice = [_advice_from_opportunity(i, op) for i, op in enumerate(top, 1)]

    risks_note = ""
    if report.risks:
        risks_note = "\n".join(f"• {r}" for r in report.risks[:5])

    blockers_note = ""
    if report.blockers:
        blockers_note = "\n".join(f"• {b}" for b in report.blockers[:5])

    headline = "Есть что улучшить" if advice else "Базовая структура на месте"
    if any(o.id in ("init_git", "add_tests") for o in top):
        headline = "Сначала закройте фундамент (git / тесты)"

    draft = opportunities_as_plan_hints(report, limit=limit)

    return AdvisorReport(
        headline=headline,
        situation=_situation_text(report),
        advice=advice,
        risks_note=risks_note,
        blockers_note=blockers_note,
        analysis={
            "kind": report.kind,
            "py_files": report.py_files,
            "test_files": report.test_files,
            "mode": report.mode,
        },
        plan_draft=draft,
    )


def draft_living_steps(advisor: AdvisorReport) -> list[dict[str, Any]]:
    """Plan-step shaped dicts (id, action, note) — caller confirms before LivingPlan.replan."""
    steps = []
    for i, a in enumerate(advisor.advice):
        steps.append({
            "id": a.opportunity_id or f"adv-{i+1}",
            "action": a.suggested_action or a.title,
            "note": a.why[:200],
            "status": "PENDING",
            "complexity": 2 if a.category in ("docs", "cleanup") else 3,
            "meta": {"source": "development_advisor", "category": a.category},
        })
    return steps


def format_session_opening(project_root: str | Path, *, limit: int = 3) -> str:
    """Short text for session start / UI banner."""
    adv = advise(project_root, limit=limit, use_index=False)
    lines = [adv.headline, adv.situation]
    for a in adv.advice:
        lines.append(f"  → {a.rank}. {a.title}")
    return "\n".join(lines)
