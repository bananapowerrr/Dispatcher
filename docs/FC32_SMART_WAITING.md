# FC-32 Smart Waiting

Pause **emit** (and optionally run) when blocked; resume when clear.

## Reasons

| Code | Meaning |
|------|---------|
| `waiting_decision` | Open FC-30 DecisionItem |
| `policy_ask` | FC-31 says ASK on conflicts |
| `policy_block` | Autopilot off / BLOCK |
| `defer_to_night` | Complex steps, daytime |
| `manual_pause` | Explicit pause |
| `ready` | No blockers |

## API

- `evaluate_wait(plan=, decisions=, conflicts=, …) → WaitState`
- `filter_emit_steps(steps, wait) → (allow, hold)`
- `after_decision_resolved(queue, plan) → WaitState`

`can_run=True` with `can_emit=False` allows in-flight work while new plan steps stay held.

## Next

FC-33 Estimation · FC-34 Night Mode polish · FC-35 Autonomous Loop  
FC-37 Project Intelligence (roadmap) after wait gate is stable.
