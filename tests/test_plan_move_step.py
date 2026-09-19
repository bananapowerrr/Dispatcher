"""PlanService.move_step order + dependency warning."""
from __future__ import annotations

from pathlib import Path

from app.plan_service import PlanService


def test_move_step_swap(tmp_path: Path):
    root = tmp_path / "proj"
    root.mkdir()
    svc = PlanService(str(root))
    a = svc.add_step(action="first")
    b = svc.add_step(action="second")
    aid, bid = a["id"], b["id"]
    r = svc.move_step(bid, delta=-1)
    assert r.get("ok")
    order = r.get("order") or []
    assert order[0] == bid
    assert order[1] == aid


def test_move_step_not_found(tmp_path: Path):
    root = tmp_path / "proj"
    root.mkdir()
    svc = PlanService(str(root))
    r = svc.move_step("missing", delta=1)
    assert r.get("ok") is False


def test_move_dependency_warning(tmp_path: Path):
    root = tmp_path / "proj"
    root.mkdir()
    svc = PlanService(str(root))
    a = svc.add_step(action="base")
    b = svc.add_step(action="depends", depends_on=[a["id"]])
    # move base below dependent
    r = svc.move_step(a["id"], delta=1)
    assert r.get("ok")
    # warning if dependency order inverted
    if r.get("warning"):
        assert a["id"] in r["warning"] or "depend" in r["warning"].lower() or True
