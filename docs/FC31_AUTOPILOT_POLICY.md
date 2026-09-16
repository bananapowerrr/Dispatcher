# FC-31 Autopilot Policy

Gate: **AUTO** / **ASK** / **BLOCK** before conflict resolution or task emission.

## Modes (`AGENTBUS_AUTOPILOT_MODE`)

| Mode | LOW | MEDIUM | HIGH |
|------|-----|--------|------|
| off | ASK | ASK | ASK |
| cautious | AUTO | ASK | ASK |
| balanced | AUTO | AUTO | ASK |
| full | AUTO | AUTO | ASK |
| night_full | AUTO | AUTO* | ASK |

\* HIGH always **ASK** (safety floor).

Feature flag `autopilot=false` → emit **BLOCK**, conflicts **ASK**.

## API

- `decide_for_conflict(conflict)`
- `decide_emit_tasks(complexity=…)`
- `decide_pipeline(conflicts)`
- `PolicyDecision.format_human()`

## Integration

```
detect_conflicts → decide_pipeline
  AUTO → apply_conflict_resolution
  ASK  → DecisionQueue.enqueue_conflict (FC-30)
  BLOCK → skip emit
```

## Next

FC-32 Smart Waiting — pause/resume when blocked on decisions or night window.
