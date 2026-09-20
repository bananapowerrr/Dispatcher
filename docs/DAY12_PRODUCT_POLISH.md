# Day 12 — Product polish around frozen runtime

**Does not change** FSM / intake / verification gate / executor / DONE gate.

## 1. Multi-project LocalQueue isolation

**Problem:** `get_local_queue(root)` ignored `root` after first call (single global).

**Fix:** `src/core/local_queue.py` — pool keyed by resolved project root.

```
proj_a queue  ≠  proj_b queue
claim(a) never returns task from b
```

Tests: `tests/test_multi_project_queue_day12.py`

## 2. Recovery / replan UX copy

**New:** `src/app/recovery_ux.py`

| Helper | Input | Output |
|--------|-------|--------|
| `format_replan_result` | `replan_after_error` dict | chat summary |
| `format_task_outcome_for_plan` | `apply_task_outcome` dict | history note |
| `format_block_reason` | `plan_blocks_enqueue` dict | pause line |
| `format_recovery_bundle` | error + plan + replan + attempts | multi-line chat |

Uses existing `core.error_ux.humanize_error` / `format_retry_status`.

Tests: `tests/test_recovery_ux_day12.py`

## 3. pack_run_evidence triage

`scripts/pack_run_evidence.py` — section `## triage` with `classify_error` code + hint when `result.json` / stderr present.

## Run

```bash
PYTHONPATH=src:. pytest -q \
  tests/test_multi_project_queue_day12.py \
  tests/test_recovery_ux_day12.py
```

## Out of scope

- Runtime claim loop changes
- New FSM states
- UI panel rewrite (wiring recovery_ux into chat is optional follow-up)
