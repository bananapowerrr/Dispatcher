# FC-27 Dynamic Queue

**Rule:** Living Plan is source of truth. Queue is a *projection*.

```
LivingPlan.eligible_for_queue()
        ↓
sync_plan_to_queue()
        ↓
desktop LocalQueue  and/or  channels/*/incoming
```

## API

| Function | Purpose |
|----------|---------|
| `sync_plan_to_queue(plan, …)` | emit eligible steps |
| `sync_from_disk(project_root)` | load plan + emit |
| `on_task_terminal(plan, task_id=, status=)` | DONE/ERROR → step status |
| `mark_step_emitted` | idempotent meta.emitted |

## Idempotency

Step `meta.emitted` / `meta.task_id` prevent re-queue. SUPERSEDED steps never emit.

## Next

FC-28 Context Intake — classify user messages before creating plan steps.
