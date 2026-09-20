# -*- coding: utf-8 -*-
"""Day-3: pure git safety policies (unit-testable without a real repo).

Complements safety/gitops.GitOps — does not call git. Runtime keeps using GitOps
for actual checkout/unlink; this module documents and validates the rules.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable


@dataclass
class SafetyDecision:
    ok: bool
    action: str  # commit | discard | block | skip
    paths: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "action": self.action,
            "paths": list(self.paths),
            "skipped": list(self.skipped),
            "reason": self.reason,
        }


def paths_safe_to_commit(
    *,
    stage: Iterable[str],
    outside: Iterable[str],
    conflicted: Iterable[str],
) -> SafetyDecision:
    """Commit only stage paths; block if outside or conflicted present."""
    stage_l = sorted({str(p).replace("\\", "/") for p in stage if p})
    outside_l = sorted({str(p).replace("\\", "/") for p in outside if p})
    conflict_l = sorted({str(p).replace("\\", "/") for p in conflicted if p})
    if outside_l or conflict_l:
        return SafetyDecision(
            ok=False,
            action="block",
            paths=[],
            skipped=outside_l + conflict_l,
            reason="outside task.files or user conflict — no commit",
        )
    if not stage_l:
        return SafetyDecision(ok=True, action="skip", reason="nothing to commit")
    return SafetyDecision(ok=True, action="commit", paths=stage_l, reason="task-only paths")


def paths_safe_to_discard(
    *,
    created: Iterable[str],
    changed: Iterable[str],
    baseline_modified: Iterable[str],
    baseline_untracked: Iterable[str],
    conflicted: Iterable[str] | None = None,
) -> SafetyDecision:
    """Discard only task-created/changed paths that were clean at baseline.

    Never returns paths that were already dirty/untracked before the task
    or listed as conflicted.
    """
    base_mod = {str(p).replace("\\", "/") for p in baseline_modified}
    base_un = {str(p).replace("\\", "/") for p in baseline_untracked}
    conf = {str(p).replace("\\", "/") for p in (conflicted or [])}
    protected = base_mod | base_un | conf

    discard: list[str] = []
    skipped: list[str] = []

    for p in created:
        path = str(p).replace("\\", "/")
        if not path:
            continue
        if path in protected:
            skipped.append(path)
            continue
        discard.append(path)

    for p in changed:
        path = str(p).replace("\\", "/")
        if not path:
            continue
        if path in protected:
            skipped.append(path)
            continue
        discard.append(path)

    discard = sorted(set(discard))
    skipped = sorted(set(skipped))
    return SafetyDecision(
        ok=True,
        action="discard" if discard else "skip",
        paths=discard,
        skipped=skipped,
        reason="task-only discard; user dirty paths skipped",
    )


def forbid_reset_hard() -> bool:
    """Policy flag: AgentBus must never use git reset --hard on user trees."""
    return True


def is_agentbus_branch(name: str) -> bool:
    return str(name or "").strip().startswith("agentbus/task-")


def branch_delete_allowed(name: str) -> bool:
    """Only agentbus/task-* may be force-deleted by cleanup."""
    return is_agentbus_branch(name)
