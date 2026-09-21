# Day 16 — Worker Router product surface

**Does not replace** `router.select_executor` or Runtime claim/execute loop.  
**Does not change** FSM / intake / verification / DONE gate.

## Gap (GitHub audit)

`plan_route` / `RouteDecision` existed (Day 8) but were only referenced from:

- `tests/test_worker_route_day8.py`
- `docs/DAY8_WORKER_ROUTER.md`

Runtime still calls `select_executor` directly (`runtime.py`, `rp_llm.py`, `runtime_ops.py`).

## Day-16 adds

### `core/worker_route_surface.py`

| Helper | Role |
|--------|------|
| `route_for_task(message, …)` | → `dict` (RouteDecision.to_dict) |
| `format_route_for_chat(…)` | multi-line `WORKER ROUTE` for System chat |
| `format_route_for_doctor(…)` | sample live-coding task route |
| `next_fallback_after_error(…)` | wrap `next_after_failure` |
| `route_surface_summary()` | matrix/acceptance row |

### Doctor

`utils/diagnose.py` prints:

```
--- worker route (sample) ---
WORKER ROUTE
  primary: …
  fallback: …
```

Non-fatal if route planning fails.

## Still out of scope

- Replacing `select_executor` inside Runtime
- Parallel workers / new providers
- Auto-fallback mutation of running tasks

## Tests

```bash
PYTHONPATH=src:. pytest -q tests/test_worker_route_day16.py
```

## Path toward LIVE-001

```
Chat task
  → (optional) format_route_for_chat  # explain
  → Runtime select_executor           # unchanged
  → Aider / Ollama
```
