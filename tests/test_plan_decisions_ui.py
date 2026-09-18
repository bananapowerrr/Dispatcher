"""Plan DecisionQueue list + policy gate (offline)."""
from __future__ import annotations

from pathlib import Path

from app.plan_service import (
    apply_input_policy,
    classify_plan_input,
    list_open_plan_decisions,
    resolve_plan_decision,
)


def test_classify_modify_replan():
    assert classify_plan_input("перепланируй с нуля") == "REPLAN"
    assert classify_plan_input("на самом деле нужен oauth") == "MODIFY"
    assert classify_plan_input("обычный фикс бага") == "INDEPENDENT"


def test_modify_enqueues_decision(tmp_path: Path):
    root = tmp_path
    (root / ".agentbus").mkdir(parents=True)
    out = apply_input_policy(root, "на самом деле нужен oauth", enqueue_decision=True)
    assert out["classification"] == "MODIFY"
    assert out["requires_decision"] is True
    assert out.get("decision_id")
    assert out["applied"] is False
    open_items = list_open_plan_decisions(root)
    assert any(x.get("id") == out["decision_id"] for x in open_items)


def test_dismiss_keeps_plan_empty(tmp_path: Path):
    root = tmp_path
    (root / ".agentbus").mkdir(parents=True)
    out = apply_input_policy(root, "перепланируй архитектуру", enqueue_decision=True)
    did = out["decision_id"]
    assert did
    # option A is typically dismiss — resolve with first option id from item
    items = list_open_plan_decisions(root)
    item = next(x for x in items if x["id"] == did)
    opt_id = item["options"][0]["id"]
    r = resolve_plan_decision(root, did, opt_id)
    assert r.get("ok") is True
    # no longer open
    open_ids = {x["id"] for x in list_open_plan_decisions(root)}
    assert did not in open_ids
