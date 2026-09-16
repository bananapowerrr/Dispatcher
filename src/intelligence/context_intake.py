# -*- coding: utf-8 -*-
"""FC-28 Context Intake — classify user messages before plan/queue.

Not every message becomes a task. Heuristic (no LLM) first; optional meta
hook can refine later.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

# Intake kinds
COMMAND = "COMMAND"           # do something now → task / plan step
INFORMATION = "INFORMATION"   # fact about project → memory / state
CONSTRAINT = "CONSTRAINT"     # hard rule → ProjectState.constraints
DECISION = "DECISION"         # chosen option → ProjectState.decisions
QUESTION = "QUESTION"         # needs answer, not code change
FEEDBACK = "FEEDBACK"         # reaction to last result
EVIDENCE = "EVIDENCE"         # log / traceback / test output
GOAL = "GOAL"                 # high-level goal for LivingPlan.summary

KINDS = (
    COMMAND, INFORMATION, CONSTRAINT, DECISION,
    QUESTION, FEEDBACK, EVIDENCE, GOAL,
)


@dataclass
class IntakeResult:
    kind: str
    confidence: float
    text: str
    normalized: str = ""
    hints: list[str] = field(default_factory=list)
    files: list[str] = field(default_factory=list)
    should_create_task: bool = False
    should_update_state: bool = False
    should_replan: bool = False
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# --- pattern libraries (RU + EN) ---

_RE_QUESTION = re.compile(
    r"(\?|^(что|как|почему|зачем|где|когда|who|what|why|how|where)\b)",
    re.I | re.M,
)
_RE_CONSTRAINT = re.compile(
    r"(нельзя|не\s+льзя|запрещ|only\s+local|только\s+локаль|без\s+cloud|no\s+cloud|"
    r"must\s+not|don't\s+use|не\s+использовать|обязательно|constraint|"
    r"только\s+sqlite|only\s+sqlite|без\s+интернет)",
    re.I,
)
_RE_DECISION = re.compile(
    r"\b(решаем|выбрали|will\s+use|используем|переходим\s+на|go\s+with|"
    r"утверждаю|approved|берём|берем)\b",
    re.I,
)
_RE_GOAL = re.compile(
    r"\b(цель|goal|хочу\s+чтобы|нужно\s+чтобы|в итоге|epic|"
    r"сделать\s+проект|ship|релиз)\b",
    re.I,
)
_RE_FEEDBACK = re.compile(
    r"\b(не\s+то|неправильно|wrong|fix\s+it|переделай|bad|"
    r"хорошо|ok\b|lgtm|отлично|не\s+работает|still\s+broken)\b",
    re.I,
)
_RE_EVIDENCE = re.compile(
    r"(Traceback \(most recent call last\)|FAILED|ERROR:|AssertionError|"
    r"=====+.*pytest|exit code \d+|npm ERR!)",
    re.I | re.S,
)
_RE_INFO = re.compile(
    r"\b(кстати|на\s+самом\s+деле|факт|uses\s+|проект\s+использует|"
    r"we\s+use|remember|запомни|в\s+этом\s+проекте)\b",
    re.I,
)
_RE_COMMAND = re.compile(
    r"\b(добавь|исправь|сделай|напиши|refactor|fix|implement|"
    r"rename|удали|create|add\s+|write\s+|update\s+|remove\s+|"
    r"покрой\s+тестами|проведи\s+рефакторинг)\b",
    re.I,
)
_RE_REPLAN = re.compile(
    r"\b(вместо|переделаем|полностью\s+пере|cancel\s+plan|новый\s+план|"
    r"replan|instead\s+of|больше\s+не\s+нужно)\b",
    re.I,
)


def _score_patterns(text: str) -> dict[str, float]:
    scores = {k: 0.0 for k in KINDS}
    if not (text or "").strip():
        return scores
    t = text.strip()
    if _RE_EVIDENCE.search(t):
        scores[EVIDENCE] += 0.85
    if _RE_QUESTION.search(t) and len(t) < 400:
        scores[QUESTION] += 0.7
    if _RE_CONSTRAINT.search(t):
        scores[CONSTRAINT] += 0.8
    if _RE_DECISION.search(t):
        scores[DECISION] += 0.75
    if _RE_GOAL.search(t):
        scores[GOAL] += 0.65
    if _RE_FEEDBACK.search(t):
        scores[FEEDBACK] += 0.6
    if _RE_INFO.search(t):
        scores[INFORMATION] += 0.55
    if _RE_COMMAND.search(t):
        scores[COMMAND] += 0.8
    # imperative short messages → command
    if len(t) < 200 and not _RE_QUESTION.search(t) and re.match(
        r"^(please\s+)?[a-zа-яё]", t, re.I
    ):
        if re.search(r"\b(py|ts|js|md|json|yaml)\b", t, re.I) or "файл" in t.lower():
            scores[COMMAND] += 0.25
    # traceback length
    if "Traceback" in t and len(t) > 200:
        scores[EVIDENCE] += 0.3
    return scores


def classify_message(
    text: str,
    *,
    files: list[str] | None = None,
    has_attachments: bool = False,
) -> IntakeResult:
    """Classify a single user message (heuristic)."""
    raw = text or ""
    normalized = " ".join(raw.split())
    scores = _score_patterns(raw)
    if has_attachments and scores[EVIDENCE] < 0.5 and scores[COMMAND] < 0.5:
        scores[INFORMATION] = max(scores[INFORMATION], 0.4)
        scores[EVIDENCE] = max(scores[EVIDENCE], 0.35)

    kind = max(scores, key=lambda k: scores[k])
    conf = float(scores[kind])
    if conf < 0.35:
        # default: short text without markers → INFORMATION; longer imperative → COMMAND
        if len(normalized) < 80 and not files:
            kind, conf = INFORMATION, 0.4
        else:
            kind, conf = COMMAND, 0.45

    # mentions → files
    try:
        from intelligence.chat_parser import parse_mentions
        mentioned = parse_mentions(raw)
    except Exception:
        mentioned = []
    all_files = list(dict.fromkeys(list(files or []) + mentioned))

    should_task = kind == COMMAND and conf >= 0.4
    should_state = kind in (INFORMATION, CONSTRAINT, DECISION, GOAL)
    should_replan = bool(_RE_REPLAN.search(raw)) or (
        kind == DECISION and conf >= 0.7
    )

    hints: list[str] = []
    if should_task:
        hints.append("enqueue_or_plan_step")
    if kind == CONSTRAINT:
        hints.append("project_state.add_constraint")
    if kind == DECISION:
        hints.append("project_state.add_decision")
    if kind == GOAL:
        hints.append("living_plan.summary / project_state.goal")
    if kind == INFORMATION:
        hints.append("session_memory or project_state")
    if kind == EVIDENCE:
        hints.append("attach_to_last_task or feedback")
    if kind == QUESTION:
        hints.append("answer_or_clarify")
    if kind == FEEDBACK:
        hints.append("retry_or_replan")
    if should_replan:
        hints.append("living_plan.replan")

    return IntakeResult(
        kind=kind,
        confidence=round(min(1.0, conf), 3),
        text=raw[:8000],
        normalized=normalized[:2000],
        hints=hints,
        files=all_files,
        should_create_task=should_task,
        should_update_state=should_state,
        should_replan=should_replan,
        meta={"scores": {k: round(v, 3) for k, v in scores.items() if v > 0}},
    )


def apply_intake_to_state(
    result: IntakeResult,
    *,
    project_root: str | None = None,
) -> list[str]:
    """Optional side-effects on ProjectState / SessionMemory. Returns actions taken."""
    actions: list[str] = []
    if not result.should_update_state and result.kind not in (CONSTRAINT, DECISION, GOAL, INFORMATION):
        return actions
    if not project_root:
        return actions
    try:
        from intelligence.project_state import load_project_state, save_project_state
        st = load_project_state(project_root)
        if result.kind == CONSTRAINT:
            st.add_constraint(result.normalized or result.text)
            actions.append("constraint")
        elif result.kind == DECISION:
            st.add_decision(result.normalized or result.text)
            actions.append("decision")
        elif result.kind == GOAL:
            st.set_goal(result.normalized or result.text)
            actions.append("goal")
        elif result.kind == INFORMATION:
            st.meta.setdefault("notes", [])
            if isinstance(st.meta["notes"], list):
                st.meta["notes"].append((result.normalized or result.text)[:300])
                st.meta["notes"] = st.meta["notes"][-30:]
            actions.append("note")
        if actions:
            save_project_state(project_root, st)
    except Exception:
        pass
    return actions
