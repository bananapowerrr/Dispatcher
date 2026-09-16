# -*- coding: utf-8 -*-
"""FC-29 Conflict Resolution — structured CONFLICT before silent replan.

Supervisor/intake must not quietly add opposing tasks. Emit a ConflictRecord;
Runtime/Policy or human decides apply vs ask.
"""
from __future__ import annotations

import re
import time
from dataclasses import asdict, dataclass, field
from typing import Any

from intelligence.living_plan import LivingPlan, LivingStep, is_active, normalize_status
from intelligence.project_state import ProjectState


@dataclass
class ConflictRecord:
    """One detected conflict between current plan/state and new intake."""

    id: str
    topic: str
    current: str
    new: str
    affected_step_ids: list[str] = field(default_factory=list)
    recommendation: str = "replan"  # replan | ask | ignore | merge
    risk: str = "MEDIUM"  # LOW | MEDIUM | HIGH
    reason: str = ""
    created_at: float = field(default_factory=time.time)
    status: str = "OPEN"  # OPEN | RESOLVED | DISMISSED
    resolution: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def format_human(self) -> str:
        lines = [
            f"CONFLICT [{self.risk}] {self.topic}",
            f"  Current: {self.current[:200]}",
            f"  New:     {self.new[:200]}",
        ]
        if self.affected_step_ids:
            lines.append(f"  Affected steps: {', '.join(self.affected_step_ids)}")
        lines.append(f"  Recommendation: {self.recommendation}")
        if self.reason:
            lines.append(f"  Reason: {self.reason[:300]}")
        return "\n".join(lines)


# topic detectors: (topic, pattern_current, pattern_new) applied on combined text space
_TOPIC_PAIRS: list[tuple[str, re.Pattern[str], re.Pattern[str]]] = [
    (
        "database",
        re.compile(r"\b(sqlite|sqlalchemy\s+sqlite)\b", re.I),
        re.compile(r"\b(postgres|postgresql|mysql|mongodb)\b", re.I),
    ),
    (
        "database",
        re.compile(r"\b(postgres|postgresql)\b", re.I),
        re.compile(r"\b(sqlite)\b", re.I),
    ),
    (
        "cloud",
        re.compile(r"\b(local-?only|только\s+локаль|ollama\s+only|без\s+cloud)\b", re.I),
        re.compile(r"\b(openrouter|siliconflow|cloud\s+api|openai)\b", re.I),
    ),
    (
        "cloud",
        re.compile(r"\b(cloud|openrouter|paid\s+api)\b", re.I),
        re.compile(r"\b(только\s+локаль|local-?only|no\s+cloud|без\s+облак)\b", re.I),
    ),
    (
        "auth",
        re.compile(r"\b(jwt|session\s+auth|старая\s+авторизац)\b", re.I),
        re.compile(r"\b(oauth|oidc|новая\s+авторизац|keycloak)\b", re.I),
    ),
    (
        "test_runner",
        re.compile(r"\b(pytest)\b", re.I),
        re.compile(r"\b(unittest|nose|vitest|jest)\b", re.I),
    ),
    (
        "package_manager",
        re.compile(r"\b(poetry|pipenv)\b", re.I),
        re.compile(r"\b(uv\b|pdm|hatch)\b", re.I),
    ),
]


def _collect_corpus(plan: LivingPlan | None, state: ProjectState | None) -> str:
    parts: list[str] = []
    if plan:
        parts.append(plan.summary or "")
        for s in plan.steps:
            if is_active(s.status) or normalize_status(s.status) == "DONE":
                parts.append(f"{s.action} {s.target} {s.note}")
    if state:
        parts.append(state.goal or "")
        parts.append(state.architecture or "")
        parts.extend(state.constraints)
        parts.extend(state.decisions)
    return "\n".join(parts)


def _affected_steps(plan: LivingPlan | None, topic: str, new_text: str) -> list[str]:
    if not plan:
        return []
    keys = {
        "database": ("sqlite", "postgres", "mysql", "db", "баз"),
        "cloud": ("cloud", "openrouter", "ollama", "local", "локал"),
        "auth": ("auth", "jwt", "oauth", "login", "авториз"),
        "test_runner": ("test", "pytest", "unittest"),
        "package_manager": ("poetry", "pip", "uv", "deps", "зависимост"),
    }.get(topic, ())
    out: list[str] = []
    blob_new = new_text.lower()
    for s in plan.steps:
        if not is_active(s.status):
            continue
        blob = f"{s.action} {s.target} {s.note}".lower()
        if any(k in blob for k in keys) or any(k in blob_new for k in keys if k in blob):
            out.append(s.id)
    return out


def detect_conflicts(
    new_text: str,
    *,
    plan: LivingPlan | None = None,
    state: ProjectState | None = None,
    intake_kind: str = "",
) -> list[ConflictRecord]:
    """Heuristic conflicts between new message and current plan/state."""
    new_text = (new_text or "").strip()
    if not new_text:
        return []
    current = _collect_corpus(plan, state)
    if not current.strip():
        return []

    found: list[ConflictRecord] = []
    seen_topics: set[str] = set()

    for topic, pat_cur, pat_new in _TOPIC_PAIRS:
        if not pat_new.search(new_text):
            continue
        if not pat_cur.search(current):
            continue
        # both sides present → conflict
        key = topic
        if key in seen_topics:
            continue
        seen_topics.add(key)
        cur_m = pat_cur.search(current)
        new_m = pat_new.search(new_text)
        risk = "HIGH" if topic in ("database", "auth") else "MEDIUM"
        if intake_kind == "CONSTRAINT":
            risk = "HIGH"
        rec = "ask" if risk == "HIGH" else "replan"
        affected = _affected_steps(plan, topic, new_text)
        found.append(
            ConflictRecord(
                id=f"c-{topic}-{int(time.time()) % 100000}",
                topic=topic,
                current=(cur_m.group(0) if cur_m else topic),
                new=(new_m.group(0) if new_m else new_text[:80]),
                affected_step_ids=affected,
                recommendation=rec,
                risk=risk,
                reason=f"New input conflicts with existing {topic} direction",
            )
        )

    # constraint vs existing decision opposite keywords
    if state and state.constraints:
        joined_c = " ".join(state.constraints).lower()
        if re.search(r"local|локал|no cloud|без cloud", joined_c, re.I) and re.search(
            r"\b(openrouter|siliconflow|cloud api)\b", new_text, re.I
        ):
            if "cloud" not in seen_topics:
                found.append(
                    ConflictRecord(
                        id=f"c-constraint-cloud-{int(time.time()) % 100000}",
                        topic="cloud",
                        current="constraint: local-only",
                        new=new_text[:120],
                        affected_step_ids=[],
                        recommendation="ask",
                        risk="HIGH",
                        reason="Violates existing local-only constraint",
                    )
                )

    return found


def apply_conflict_resolution(
    conflict: ConflictRecord,
    plan: LivingPlan,
    *,
    resolution: str = "",
    replace_action: str = "",
) -> list[str]:
    """Apply a resolution to the living plan. Returns action tags.

    resolution: replan | dismiss | supersede_affected
    """
    actions: list[str] = []
    res = (resolution or conflict.recommendation or "replan").lower()
    if res in ("dismiss", "ignore"):
        conflict.status = "DISMISSED"
        conflict.resolution = res
        actions.append("dismissed")
        return actions

    if res in ("replan", "supersede_affected", "ask"):
        # ask still can soft-supersede only if caller forces; default supersede affected on replan
        if res == "ask":
            conflict.status = "OPEN"
            actions.append("waiting_decision")
            return actions
        supersede_ids = list(conflict.affected_step_ids)
        add: list[LivingStep] = []
        if replace_action.strip():
            add.append(
                LivingStep(
                    id=f"{conflict.topic}_new",
                    action=replace_action.strip()[:500],
                    status="PENDING",
                    meta={"from_conflict": conflict.id},
                )
            )
        plan.replan(
            supersede_ids=supersede_ids,
            add_steps=add,
            reason=f"conflict:{conflict.topic}:{conflict.reason}"[:300],
        )
        conflict.status = "RESOLVED"
        conflict.resolution = res
        actions.append("replan")
        actions.extend([f"supersede:{i}" for i in supersede_ids])
    return actions
