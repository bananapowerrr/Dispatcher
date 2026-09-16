# FC-26 Living Plan

**Status:** implemented offline  
**Modules:** `src/intelligence/living_plan.py`, `task_graph.py` (ready/all_finished)

## Idea

```
PLAN v1  →  work  →  new info  →  Supervisor  →  PLAN v2
```

- **DONE / ERROR** never rewritten to SUPERSEDED
- Only **future** steps can become SUPERSEDED / OBSOLETE / REPLACED / CANCELLED
- Each `replan()` bumps `version` and stores a compact snapshot in `history`

## API

| Symbol | Role |
|--------|------|
| `LivingPlan` / `LivingStep` | versioned plan |
| `supersede(id, replacement=…)` | retire future step, optional new step |
| `replan(supersede_ids=…, add_steps=…)` | PLAN vN |
| `eligible_for_queue()` | active steps with deps DONE |
| `load/save_living_plan` | `.agentbus/living_plan.json` (+ `.md`) |
| `LivingPlan.from_pev_plan` | import classic `pev_loop.Plan` |

## TaskGraph

Inactive statuses count as **closed** for `all_finished()` and are skipped by `ready()`.

## Next

**FC-27** Dynamic Queue — emit only `eligible_for_queue()` into desktop/file-bus.
