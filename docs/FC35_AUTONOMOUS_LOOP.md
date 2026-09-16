# FC-35 Autonomous Loop

One **supervisor tick** — no worker execution.

```
load plan/state/decisions
        ↓
expire soft decisions
        ↓
detect conflicts (optional message)
        ↓
policy → AUTO replan | ASK → DecisionQueue
        ↓
evaluate_wait (decision / policy / night / pause)
        ↓
estimates (FC-33)
        ↓
night_batch_summary (FC-34)
        ↓
filter_emit_steps (FC-32)
        ↓
sync_plan_to_queue (FC-27)   ← only if can_emit
        ↓
TickResult
```

## API

```python
from intelligence.autonomous_loop import run_tick, run_tick_safe

result = run_tick(
    project_root,
    max_emit=4,
    use_desktop_queue=True,
    new_message="",   # optional intake
)
print(result.format_human())
```

## TickResult

- `waited`, `wait`, `emitted`, `held_steps`, `open_decisions`
- `night`, `plan_version`, `batch`, `actions`, `errors`

## Integration

Dispatcher / UI timer:

```python
if feature_flags.is_enabled("autopilot"):
    run_tick_safe(BASE_DIR)
```

Workers still run only via normal claim → execute → verify path.

## Done line FC-26…35

Supervisor contour offline is complete. Next parallel tracks:

- **FC-36** Adaptive Runtime (capability scan)
- **FC-37** Project Intelligence (analysis / advisor)
- **LIVE** acceptance on real machine
