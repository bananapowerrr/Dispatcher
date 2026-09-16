# FC-37G Architecture Interview

Unknowns from FC-37F → `DecisionQueue` (WAITING_DECISION).

```python
from intelligence.architecture_interview import start_interview, apply_architecture_answer
from intelligence.decision_queue import DecisionQueue

dq = DecisionQueue(path=".agentbus/decisions.json")
print(start_interview(".", decisions=dq).format_human())
# after user picks A/B/C:
apply_architecture_answer(dq, decision_id, "A", state=project_state)
```

## Rules

- Max few questions (`limit=3`)
- HIGH risk → no auto-timeout
- Answers go to `ProjectState.decisions`
- LivingPlan not auto-changed
- Duplicates skipped if already open

## Next

**37H** Architecture blockers — autopilot pause while interview open  
**37J** Supervisor uses decisions when planning
