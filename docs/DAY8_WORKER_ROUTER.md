# Day 8 — Worker Router (product layer)

**Does not replace** `router.select_executor` or Runtime worker loop.  
**Does not change** Worker Contract / FSM / DONE gate.

## Goal

Explainable routing for mass product:

```
Task
  ↓
plan_route()
  ↓
primary + fallback chain + reasons
  ↓
Runtime still runs selected worker via existing path
```

## API

```python
from core.worker_route import plan_route, next_after_failure

decision = plan_route(task_dict, workers=None, health=health)
print(decision.format_human())
# WORKER ROUTE
#   primary: aider_local
#   fallback: opencode_zen → …
#   complexity=2  type=general
#   · …

decision.to_dict()  # for UI / run log
```

After failure:

```python
nxt = next_after_failure(workers, tried=["aider_local"], error="Connection refused")
```

## Building blocks (existing)

| Module | Role |
|--------|------|
| `router.select_executor` | score + pick primary |
| `fallback.order_candidates` / `next_fallback` | chain after failure |
| `worker_diagnostics` | live stack readiness |
| `capability_router` | soft local-first hints |

## Day-8 adds

`core/worker_route.py` — single `RouteDecision` for doctor, chat system lines, run evidence.

## Tests

```bash
PYTHONPATH=src:. pytest -q tests/test_worker_route_day8.py
```

## Out of scope

- Changing how executor launches Aider
- New providers
- Parallel workers
