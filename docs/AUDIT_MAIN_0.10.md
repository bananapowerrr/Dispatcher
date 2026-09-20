# AgentBus / NVCode — audit of current main (offline, 2026-09-20)

**Source of truth for *current* offline readiness.** Historical handoffs live in `docs/archive/`.

## Verdict

| Layer | Status | Notes |
|-------|:------:|-------|
| Core Runtime (FSM, intake, verify, executor, reclaim) | ✅ offline | DONE only after verify |
| TaskService fail-closed enqueue | ✅ | `soft_intake=False`; reject → no LocalQueue.put |
| Plan terminal authority | ✅ | DONE/ERROR need `task_id` (runtime hook) |
| Plan orphan reconcile | ✅ | `IN_PROGRESS` w/o task_id → PENDING on `analyze()` |
| Doctor readiness + board | ✅ | config, workers, CLI probes, `format_board_text` |
| Offline acceptance matrix | ✅ | `scripts/offline_acceptance_matrix.py` → 10/10 |
| UI product shell | ✅ offline | empty-states, Plan/Queue/Chat; no new panels |
| **Live worker path** | ❌ not proven | Chat → Ollama/Aider → file change → verify → DONE |

**Product readiness (honest): ~70% overall; core offline ~85–90%; live = 0 until PC.**

## Canonical path (must hold)

```
CHAT / LocalQueue / file-bus
        ↓
  intake (fail-closed)
        ↓
  FSM: PENDING → CLAIMED → PROCESSING → VERIFYING
        ↓
  skill | LLM worker
        ↓
  VerificationEngine (fail-closed gates)
        ↓
  DONE | ERROR | RETRY | DEFERRED
        ↓
  Plan terminal hook (task_id) · History · Metrics
```

**Rule:** UI, Plan, Worker, LLM must **not** declare DONE alone.

## P0 closed in code (Drive worktree)

1. TaskService — external intake fail-closed  
2. SkillLearner — no stub `.py` without real `source=`  
3. ProjectWorkflow — any blocker blocks enqueue; reconcile on analyze  
4. PlanService — terminal status only with `task_id`  
5. Custom loader — sandbox before `exec_module`  
6. LocalQueue — per resolved project root  
7. Doctor — CLI tools + board in `doctor_full_text`  
8. Offline matrix script  

## Offline gate (run before live)

```bash
PYTHONPATH=src:. python scripts/offline_acceptance_matrix.py
PYTHONPATH=src:. python -m pytest -q \
  tests/test_p0_fail_closed.py \
  tests/test_p1_loader_queue.py \
  tests/test_p1_reconcile_doctor.py \
  tests/test_analyze_reconcile.py \
  tests/test_plan_done_ui_message.py \
  tests/test_status_board_text.py
python scripts/smoke_offline.py
python scripts/live_smoke.py --mock
python dispatcher.py --doctor
```

## Explicitly NOT doing now

- New AI features, MCP, RAG 2.0, parallel > 1  
- UI redesign / new panels  
- Claiming READY without usable worker binary + model  

## Next (machine only) — GPT live package

1. Doctor must show usable stack for **this** machine  
2. One happy path: chat → queue → worker → real file diff → verify PASS → DONE  
3. One fail path: bad change → verify FAIL → not DONE → retry/ERROR  
4. Restart: plan/task linkage survives  
5. Then packaging / intelligence layers  

See [LIVE_ACCEPTANCE.md](LIVE_ACCEPTANCE.md), [CONTRACTS.md](CONTRACTS.md), [STATUS_OFFLINE.md](STATUS_OFFLINE.md).
