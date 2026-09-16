# -*- coding: utf-8 -*-
import json
from pathlib import Path

from sub_agent import SubAgent, spawn_subtasks


def test_spawn_and_registry(tmp_path: Path):
    sa = SubAgent(tmp_path, channel="gpt")
    res = sa.spawn_many(
        [
            {"message": "fix a.py", "files": ["a.py"]},
            {"message": "fix b.py", "files": ["b.py"]},
        ],
        parent_id="parent1",
        project="demo",
    )
    assert len(res.task_ids) == 2
    for tid in res.task_ids:
        p = tmp_path / "channels" / "gpt" / "incoming" / f"{tid}.json"
        assert p.is_file()
        data = json.loads(p.read_text(encoding="utf-8"))
        assert data["metadata"]["is_subtask"] is True
        assert data["metadata"]["parent_id"] == "parent1"
    assert sa.load_registry("parent1") == res.task_ids


def test_progress_states(tmp_path: Path):
    sa = SubAgent(tmp_path, channel="gpt")
    res = sa.spawn_many(
        [{"message": "one"}, {"message": "two"}],
        parent_id="p2",
    )
    tid0, tid1 = res.task_ids
    # move one to done
    src = tmp_path / "channels" / "gpt" / "incoming" / f"{tid0}.json"
    done = tmp_path / "channels" / "gpt" / "done"
    done.mkdir(parents=True, exist_ok=True)
    src.rename(done / f"{tid0}.json")
    report = sa.progress("p2")
    assert report.total == 2
    assert report.done == 1
    assert report.pending == 1
    assert not report.finished


def test_cancel_pending(tmp_path: Path):
    sa = SubAgent(tmp_path, channel="gpt")
    res = sa.spawn_many(
        [{"message": "x"}, {"message": "y"}],
        parent_id="p3",
    )
    cancelled = sa.cancel_pending("p3")
    assert set(cancelled) == set(res.task_ids)
    report = sa.progress("p3")
    assert report.error == 2
    assert report.pending == 0


def test_feature_flag_disables_spawn(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AGENTBUS_FEATURE_SUB_AGENTS", "0")
    import feature_flags as ff
    ff.reload_flags()
    res = spawn_subtasks(tmp_path, [{"message": "nope"}], parent_id="px")
    assert res.task_ids == []
    monkeypatch.setenv("AGENTBUS_FEATURE_SUB_AGENTS", "1")
    ff.reload_flags()
