# FC-29 Conflict Resolution

Detect opposing directions before enqueue/replan.

```
new message + LivingPlan + ProjectState
        ↓
detect_conflicts()
        ↓
ConflictRecord (OPEN)
        ↓
apply_conflict_resolution(replan|dismiss|ask)
```

## ConflictRecord

- topic, current, new
- affected_step_ids
- recommendation: replan | ask | ignore
- risk: LOW | MEDIUM | HIGH

HIGH (db/auth/constraint) → prefer **ask** (FC-30 Decision Queue).

## Next

FC-30 WAITING_DECISION / Human Decision Queue.
