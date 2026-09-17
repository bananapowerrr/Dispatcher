# P1 — Silent Exception Audit (offline)

**Scope:** runtime / rp_* / verify / reclaim / plan / queue  
**Date:** 2026-09-18  
**Goal:** classify handlers that can hide task/plan/verification state loss.

## Classification legend

| Tag | Meaning |
|-----|---------|
| **SAFE** | Optional metrics, UI emit, ranking — failure OK |
| **HANDLED** | Error becomes explicit ERROR/None/status |
| **LOGGED** | Failure visible; state preserved or fail-closed |
| **DANGEROUS** | Could hide lost task, plan, verify, or queue state |

## Summary counts (approx.)

| Area | Silent-ish handlers | Notes |
|------|--------------------:|-------|
| rp_llm.py | ~37 | Mostly metrics/health/emit — SAFE if worker path still returns status |
| rp_cache.py | ~22 | Metrics + optional pev events — SAFE; cache miss returns None HANDLED |
| rp_verify.py | ~17 | Phase/metrics SAFE; budget/commit should log (often does via log.write) |
| runtime.py | ~16 | EventBus/heartbeat SAFE; plan notify LOGGED; lock release SAFE |
| rp_context.py | ~15 | Context enrichment SAFE (degrade to less context) |
| rp_lifecycle*.py | ~20 | Hooks SAFE; terminal queue errors often logged |
| reclaim.py | ~10 | OSError on lease touch SAFE with care |
| living_plan | 2 | **Was DANGEROUS → LOGGED** (this pass) |
| dynamic_queue | 2 | LOGGED |
| task_service | 6 | HANDLED + LOGGED soft intake |
| local_queue | 4 | Spill parse LOGGED |
| verification_engine | 1 | duration LOGGED |

## Fixed this pass

1. `load_living_plan` — corrupt JSON no longer silent `pass`; **warn** log.
2. `save_living_plan` — write failure **error** log + **re-raise** (fail-closed).
3. `living_plan.md` mirror — **warn** log.
4. `verification_engine` duration — **warn** log.
5. `utils/safe_log.py` — shared non-raising logger.

## Still DANGEROUS / watchlist (next P1 batch)

| Site | Risk | Recommended |
|------|------|-------------|
| `rp_verify` outer paths that `pass` after failed `_bump_verify_fails` | verify fail counter lost | log + best-effort bump |
| `rp_lifecycle` `queue.terminal` except | task stuck PROCESSING | log + retry terminal or ERROR emit |
| `reclaim` lease unlink double OSError | stale lease | already mostly OK |
| `rp_llm` health.end_task in except pass | worker slot leak | log warning |
| `runtime` file_locks.release pass | lock stuck | log warning |

## Rule going forward

> In paths that mutate **task status, plan, queue, verify gate, git rollback**:  
> never bare `except: pass`. Prefer HANDLED status or LOGGED + fail-closed.

Optional UI/metrics may stay SAFE with `pass`.

## Verification

```bash
PYTHONPATH=src:. python -c "from intelligence.living_plan import load_living_plan, save_living_plan"
pytest -q tests/test_p0_*.py tests/test_p1_*.py
```
