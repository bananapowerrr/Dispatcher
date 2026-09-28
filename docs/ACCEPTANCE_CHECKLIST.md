# Acceptance checklist (copy rows into notes)

## Offline (before live)

```
[ ] bash scripts/ci_offline.sh                     → GREEN
[ ] python scripts/offline_acceptance_matrix.py    → N/N PASS
[ ] pytest -q tests/test_chat_messages_day4.py     → PASS
[ ] python dispatcher.py --doctor                  → READY or DEGRADED+reason
[ ] python scripts/live_smoke.py --mock            → summary.md present
```

## Live sequence (first day)

```
LIVE-001 | run_id=… | PASS/FAIL | notes=
LIVE-002 | run_id=… | PASS/FAIL | notes=
LIVE-006 | run_id=… | PASS/FAIL | notes=   # verify PASS → DONE
LIVE-007 | run_id=… | PASS/FAIL | notes=   # verify FAIL → not DONE
LIVE-016 | run_id=… | PASS/FAIL | notes=   # plan → task → DONE
```

On FAIL:

```bash
python scripts/pack_run_evidence.py -o /tmp/evidence.md
# fill docs/templates/LIVE_BUG.md
```

## P0 stop conditions

- false DONE (verify fail but status DONE)
- git hard-reset lost user work
- infinite retry without terminal
