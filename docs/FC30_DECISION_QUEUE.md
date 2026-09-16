# FC-30 Human Decision Queue

When FC-29 conflict has `recommendation=ask` (HIGH risk), enqueue a **DecisionItem** instead of auto-replan.

## Flow

```
ConflictRecord (ask)
        ↓
DecisionQueue.enqueue_conflict()
        ↓
WAITING_DECISION  (blocks affected steps)
        ↓
Human chooses A / B / C
        ↓
resolve() → dismiss | replan | supersede_affected
        ↓
LivingPlan + ProjectState.decisions updated
```

## Options (default)

| ID | Action | Meaning |
|----|--------|---------|
| A | dismiss | Keep current direction |
| B | replan | Apply new direction |
| C | supersede_affected | Cancel only affected steps |

## Timeouts

| Risk | Default |
|------|---------|
| LOW | 3600s |
| MEDIUM | 7200s |
| HIGH | **no auto-timeout** (human required) |

Env: `AGENTBUS_DECISION_TIMEOUT_LOW|MEDIUM|HIGH`

## API

- `DecisionQueue.enqueue_conflict(conflict)`
- `DecisionQueue.resolve(id, option_id, plan=, state=)`
- `DecisionQueue.has_blocking(project, step_ids)`
- `DecisionQueue.expire_stale()`
- `DecisionItem.format_human()`

## Next

FC-31 Autopilot Policy — when system may proceed without human.
