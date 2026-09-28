# Day 19 — Recovery / Replan live acceptance

**Prerequisite:** LIVE-001 GREEN (Day 17) and at least LIVE-006/007 attempted (Day 18).

Does not change FSM offline. These cases prove the product recovery path on PC.

## Chain under test

```
Task → Plan step → Execute → Verify FAIL
  → analyze / recovery_ux message in chat
  → replan (new PENDING retry step; ERROR step remains history)
  → retry execute
  → Verify PASS → DONE
```

## Cases

| ID | Scenario | Expected |
|----|----------|----------|
| REC-001 | Verify FAIL once, retry succeeds | ERROR then DONE; attempts≥2; chat shows recovery lines |
| REC-002 | Retry exhausted | final ERROR; max attempts visible; no false DONE |
| REC-003 | Replan creates new step | `new_step_id` PENDING; original ERROR step still in plan history |
| REC-004 | Block: decision required | chat `⏸` decision line; no silent enqueue |
| REC-005 | Block: IN_PROGRESS active | chat pause line; next step waits |
| REC-006 | Restart mid-ERROR | no duplicate task; reclaim does not mark DONE |
| REC-007 | Chat enrichment | ERROR bubble includes humanize + attempts + replan summary (Day 14 bridge) |
| REC-008 | Evidence pack triage | `pack_run_evidence.py` → `## triage` with FAIL LAYER |

## How to log

```bash
PYTHONPATH=src:. python scripts/live_acceptance_log.py \
  --id REC-001 --result PASS --run-id <id> --notes "retry then DONE"

# on fail:
PYTHONPATH=src:. python scripts/live_acceptance_log.py \
  --id REC-002 --result FAIL --error "<paste>"
python scripts/pack_run_evidence.py --run-id <id> -o /tmp/ev.md
```

## Stop rules

- False DONE after verify fail → P0, stop
- Replan deletes/hides original ERROR step → PLAN bug, stop
- Recovery message missing in chat but runtime OK → UI (Day 14 wire check)

## Out of scope until GREEN

Night mode (Day 20), multi-project parallel, autopilot.
