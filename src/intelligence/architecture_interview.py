# -*- coding: utf-8 -*-
"""FC-37G Architecture Interview — unknowns → DecisionQueue.

Turns architecture_discovery unknowns into WAITING_DECISION items with
A/B/C options. Answers are recorded into ProjectState.decisions.
Does not mutate LivingPlan automatically.
"""
from __future__ import annotations

import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from intelligence.architecture_discovery import (
    ArchitectureMap,
    architecture_questions,
    discover_architecture,
)
from intelligence.decision_queue import DecisionItem, DecisionOption, DecisionQueue
from intelligence.project_state import ProjectState

# question substring → option templates
_OPTION_BANK: list[tuple[re.Pattern[str], list[tuple[str, str, str]]]] = [
    (
        re.compile(r"авторизац|auth", re.I),
        [
            ("A", "В API / backend (JWT/session)", "record"),
            ("B", "Через внешний провайдер (OAuth/OIDC)", "record"),
            ("C", "Пока без авторизации / отложить", "record"),
            ("D", "Ещё не решил", "defer"),
        ],
    ),
    (
        re.compile(r"источник истины|данных|хранилищ|БД|баз", re.I),
        [
            ("A", "Одна основная БД", "record"),
            ("B", "Файлы / локальный JSON", "record"),
            ("C", "Внешний API как source of truth", "record"),
            ("D", "Ещё не решил", "defer"),
        ],
    ),
    (
        re.compile(r"бизнес-логик", re.I),
        [
            ("A", "В backend / API", "record"),
            ("B", "В UI / клиенте", "record"),
            ("C", "Разделить между UI и backend", "record"),
            ("D", "Ещё не решил", "defer"),
        ],
    ),
    (
        re.compile(r"точк[аи] входа|entrypoint", re.I),
        [
            ("A", "Один главный entry (main/app)", "record"),
            ("B", "Несколько сервисов / процессов", "record"),
            ("C", "Библиотека без entrypoint", "record"),
            ("D", "Ещё не решил", "defer"),
        ],
    ),
    (
        re.compile(r"провер|тест|pytest", re.I),
        [
            ("A", "pytest в tests/", "record"),
            ("B", "Другой runner", "record"),
            ("C", "Пока без автотестов", "record"),
            ("D", "Ещё не решил", "defer"),
        ],
    ),
    (
        re.compile(r"LLM|пользователь взаимодей", re.I),
        [
            ("A", "Desktop UI / чат", "record"),
            ("B", "CLI", "record"),
            ("C", "HTTP API", "record"),
            ("D", "Ещё не решил", "defer"),
        ],
    ),
]


def _options_for_question(question: str) -> list[DecisionOption]:
    for pat, rows in _OPTION_BANK:
        if pat.search(question):
            return [
                DecisionOption(id=i, label=lab, action=act, payload={"answer": lab})
                for i, lab, act in rows
            ]
    # generic
    return [
        DecisionOption(id="A", label="Вариант по умолчанию для этого проекта", action="record", payload={}),
        DecisionOption(id="B", label="Альтернативный подход", action="record", payload={}),
        DecisionOption(id="C", label="Отложить решение", action="defer", payload={}),
        DecisionOption(id="D", label="Ещё не решил", action="defer", payload={}),
    ]


@dataclass
class InterviewResult:
    """Outcome of starting or summarizing an architecture interview."""

    enqueued: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    open_ids: list[str] = field(default_factory=list)
    architecture: dict[str, Any] = field(default_factory=dict)
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def format_human(self) -> str:
        lines = ["Architecture interview:"]
        if self.enqueued:
            lines.append(f"  Enqueued: {', '.join(self.enqueued)}")
        if self.skipped:
            lines.append(f"  Skipped (already open/answered): {len(self.skipped)}")
        if self.open_ids:
            lines.append(f"  Open: {', '.join(self.open_ids)}")
        if self.message:
            lines.append(self.message)
        return "\n".join(lines)


def _decision_id(question: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9а-яА-Я]+", "-", question.lower())[:40].strip("-")
    return f"arch-{slug or int(time.time()) % 100000}"


def make_architecture_decision(
    question: str,
    *,
    project: str = "",
    risk: str = "HIGH",
) -> DecisionItem:
    """Build one DecisionItem for an architecture unknown."""
    opts = _options_for_question(question)
    timeout = 0.0 if risk.upper() == "HIGH" else 7200.0
    now = time.time()
    return DecisionItem(
        id=_decision_id(question),
        title="Architecture: " + question[:80],
        question=question,
        options=opts,
        risk=risk.upper(),
        status="WAITING_DECISION",
        conflict_id="",
        conflict={"topic": "architecture", "question": question},
        affected_step_ids=[],  # blocks broad emit when has_blocking without step filter
        project=project,
        created_at=now,
        timeout_sec=timeout,
        expires_at=(now + timeout) if timeout > 0 else 0.0,
        meta={"source": "architecture_interview"},
    )


def start_interview(
    project_root: str | Path | None = None,
    *,
    arch: ArchitectureMap | None = None,
    decisions: DecisionQueue | None = None,
    limit: int = 3,
    project: str = "",
    skip_if_open: bool = True,
) -> InterviewResult:
    """Discover (if needed) and enqueue up to ``limit`` architecture questions."""
    if arch is None:
        if project_root is None:
            raise ValueError("project_root or arch required")
        arch = discover_architecture(project_root)

    if decisions is None:
        decisions = DecisionQueue()

    qs = architecture_questions(arch, limit=limit)
    if not qs:
        return InterviewResult(
            message="No architecture unknowns — interview not needed.",
            architecture=arch.to_dict(),
        )

    open_titles = {i.title for i in decisions.open_items(project or None)}
    open_questions = {i.question for i in decisions.open_items(project or None)}
    enqueued: list[str] = []
    skipped: list[str] = []

    for q in qs:
        question = str(q.get("question") or "")
        if not question:
            continue
        if skip_if_open and (question in open_questions or any(question[:40] in t for t in open_titles)):
            skipped.append(question[:60])
            continue
        item = make_architecture_decision(question, project=project or arch.project_root)
        # avoid id collision
        if decisions.get(item.id) and decisions.get(item.id).is_open():
            skipped.append(item.id)
            continue
        decisions.enqueue(item)
        enqueued.append(item.id)

    open_ids = [i.id for i in decisions.open_items(project or None)]
    return InterviewResult(
        enqueued=enqueued,
        skipped=skipped,
        open_ids=open_ids,
        architecture={"components": [c.id for c in arch.components], "unknowns": list(arch.unknowns)},
        message=f"Queued {len(enqueued)} architecture question(s).",
    )


def apply_architecture_answer(
    decisions: DecisionQueue,
    decision_id: str,
    option_id: str,
    *,
    state: ProjectState | None = None,
) -> dict[str, Any]:
    """Resolve interview item and record decision text into ProjectState."""
    item = decisions.get(decision_id)
    if not item:
        return {"ok": False, "error": "not_found"}
    if not item.is_open():
        return {"ok": False, "error": "not_open", "status": item.status}

    opt = next((o for o in item.options if o.id == option_id), None)
    if opt is None:
        return {"ok": False, "error": "bad_option"}

    item.status = "RESOLVED"
    item.chosen_option_id = option_id
    item.resolution = opt.action
    item.resolved_at = time.time()
    # persist if queue has path
    try:
        decisions._save()
    except Exception:
        pass

    if state is not None and opt.action in ("record", "defer", "custom"):
        text = f"Architecture: {item.question[:120]} → {opt.label}"
        try:
            state.add_decision(text)
        except Exception:
            pass

    return {
        "ok": True,
        "decision_id": decision_id,
        "option": option_id,
        "label": opt.label,
        "action": opt.action,
        "recorded": state is not None,
    }


def interview_summary(decisions: DecisionQueue, *, project: str = "") -> str:
    """Human list of open architecture decisions."""
    items = [
        i for i in decisions.open_items(project or None)
        if (i.meta or {}).get("source") == "architecture_interview"
        or str(i.title).startswith("Architecture")
    ]
    if not items:
        return "No open architecture questions."
    lines = [f"Open architecture questions: {len(items)}"]
    for i in items:
        lines.append(f"  • [{i.id}] {i.question[:100]}")
        for o in i.options[:4]:
            lines.append(f"      [{o.id}] {o.label}")
    return "\n".join(lines)
