# Day 5 — Offline hardening & acceptance pack

**Date:** 2026-09-20  
**Runtime / FSM / intake / verify gate / executor:** **FROZEN** (no changes).

## Goal

On PC return: run offline gate → doctor → mock smoke → first live.  
No infrastructure debugging on day one.

## Offline packages completed (Days 1–4)

| Day | Package | Status |
|-----|---------|:------:|
| 1 | Worker layer diagnostics + doctor integration | ✅ |
| 2 | Plan ↔ Task reconciliation / replan paths | ✅ |
| 3 | 7B context pack + git safety policies | ✅ |
| 4 | Chat product messages (progress_ux / error_ux / result_text) | ✅ |
| 5 | Acceptance suite docs + evidence packer + AGENTS.md | ✅ |

## Day-5 deliverables (this pack)

1. **`docs/LIVE_ACCEPTANCE_SUITE.md`** — 20+ scenarios (LIVE-001…022) ready for checklist rows  
2. **`docs/LIVE_RUNBOOK.md`** — first-day sequence on PC  
3. **`docs/templates/LIVE_BUG.md`** — triage template  
4. **`scripts/pack_run_evidence.py`** — read-only pack of `.agentbus/runs/<id>/`  
5. **`AGENTS.md`** — OpenCode / local agent hard rules  
6. **`docs/OFFLINE_FREEZE.md`** — allowed vs forbidden until first live  
7. Extended offline matrix checks for chat UX (no runtime touch)

## Gate before any live

```bash
bash scripts/ci_offline.sh
python scripts/offline_acceptance_matrix.py
PYTHONPATH=src pytest -q tests/test_chat_messages_day4.py tests/test_worker_diagnostics_day1.py
python dispatcher.py --doctor
python scripts/live_smoke.py --mock
```

All must be GREEN / READY (or DEGRADED with explicit reason).

## First live criterion (not optional)

```
request → plan/task → worker → real file change → verify PASS → DONE
```

False DONE = **P0 stop**.

## What is NOT in this offline pack

- MCP / RAG / embeddings / autopilot  
- FSM / DONE gate / intake contract changes  
- UI rewrite of `chat_panel.py` (Day-4 is 1-line wire on PC if needed)  
- Parallel workers  

## After 5–10 successful LIVE-00x

Only then: OpenCode + LIVE-BUG fixes. GitHub = source of truth.
