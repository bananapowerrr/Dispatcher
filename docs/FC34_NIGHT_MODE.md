# FC-34 Night Mode (polish)

Extends existing `night_scheduler.py` with estimation budget and LivingPlan selection.

## Env

| Variable | Default | Meaning |
|----------|---------|---------|
| `AGENTBUS_NIGHT_START` | 22:00 | window start |
| `AGENTBUS_NIGHT_END` | 06:00 | window end |
| `AGENTBUS_NIGHT_MAX_TASKS` | 20 | cap count |
| `AGENTBUS_NIGHT_MIN_COMPLEXITY` | 3 | defer threshold (day) |
| `AGENTBUS_NIGHT_MAX_DURATION_SEC` | 0 | 0=off; night batch duration budget |

## New API

- `select_night_tasks` — respects duration budget via `metadata.estimate`
- `select_plan_steps_for_night(plan)` — active high-complexity steps + FC-33 estimates
- `night_batch_summary(...)` — UI/supervisor preview
- `generate_morning_report_rich(...)` — durations + plan version + open decisions

## Day policy (unchanged spirit)

- Night → run
- Day + urgent → run
- Day + complexity ≥ min → `defer_to_night`
- Low complexity day → run (local routine)

## Next

FC-35 Autonomous Loop — wire wait + night + plan + decisions into one tick.
