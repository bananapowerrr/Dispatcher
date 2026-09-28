# Day 20 — Night mode constraints (docs only)

**Not implemented offline.** Do not enable autopilot/night_scheduler until LIVE-001 and REC-001 are GREEN on PC.

## Allowed shape (bounded loop)

```
eligible plan step
       ↓
execute (existing Runtime / select_executor)
       ↓
verify
   ↙       ↘
PASS       FAIL
 ↓           ↓
DONE       recovery_ux + optional replan
             ↓
           retry (max attempts)
```

## Hard limits

| Limit | Suggested default |
|-------|-------------------|
| MAX_PARALLEL_PROJECTS | 1 |
| max attempts / step | 3 |
| max tasks / night session | small finite (e.g. 10) |
| max consecutive failures | stop session |
| dangerous commands | reject (existing safety) |
| uncertainty / decision queue | **stop** — never auto-pick user decisions |
| false DONE | forbidden (verify gate unchanged) |

## Explicitly forbidden until proven live

- New AI features, MCP, RAG, embeddings memory
- Parallel multi-project night runs
- Silent policy/preset mutation from UI (Day 13.1 RO)
- Bypassing intake / DONE gate
- Auto-resolve DecisionQueue

## Enable path (later, on PC)

1. LIVE-001…010 matrix partially green
2. REC-001 retry success + REC-002 exhausted documented
3. Feature flag `night_scheduler` only after doctor READY
4. One project sandbox, local_only policy

## Offline status

This file is the contract. No Runtime code in Day 20 offline batch.
