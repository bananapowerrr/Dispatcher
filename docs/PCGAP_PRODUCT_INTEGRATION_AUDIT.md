# PC-GAP — Product Integration Gap Audit

**HEAD baseline:** `f940fdd2d419` (DEV-SYNC) · Runtime **frozen**  
**Mode:** product surface around freeze · 4-day PC-GAP window

## Chain matrix

| Transition | Code | Linked | Test | Blocks LIVE? |
|------------|------|--------|------|--------------|
| Chat → Task | `chat_panel.send_task` → `task_service.submit_payload` → `LocalQueue` | ✅ | unit/intake | No (needs PC env) |
| Task → intake | `intake_pipeline.accept_task_raw` (soft in task_service) | ✅ | intake tests | Security only |
| Plan | `plan_service` / `living_plan` / `plan_runtime_bridge` | ✅ parallel path | plan tests | Not on critical LIVE-001 path |
| Context report module | `intelligence.context_report` | ✅ module | day15 | — |
| **Context → Chat/meta** | was ❌ | **✅ PC-GAP** `product_surface.attach_context_preview` in send_task | pcgap tests | Improves worker inputs later |
| Router `select_executor` | `core.router` | ✅ Runtime | executor tests | **PC** |
| Router surface advisory | `worker_route_surface` | module ✅ | day16 | — |
| **Route → Chat/meta** | was ❌ | **✅ PC-GAP** `attach_route_preview` | pcgap | UX only |
| Worker Aider/Ollama | workers + executor | ✅ | hist. | **PC LIVE-001** |
| Diff → Verify → DONE | `rp_verify` frozen | ✅ | fail-closed | **PC** |
| ERROR → recovery_ux | `app.recovery_ux` | ✅ | day12 | — |
| **Recovery → Chat** | bridge | **✅ P0+PC-GAP** in poll ERROR | day14 | UX |
| **DONE → story** | was weak | **✅** `format_done_story` | pcgap | UX |
| Settings RO | contract + panel | **✅ Drive P0** (verify sync) | day13.1 | No |

## What still only PC can prove

1. Ollama up + model pull  
2. Aider binary + real diff  
3. Verify PASS on `test_aider.txt`  
4. End-to-end latency / reclaim under load  

## Freeze (unchanged)

FSM, intake semantics, gate_done, verify, executor process, reclaim, Runtime core, parallel >1.

## Deliverables this batch

- `src/app/product_surface.py`  
- `ui/chat_panel.py` wired: context + route System lines; DONE story; ERROR recovery  
- `ui/chat_recovery_bridge.py` with `format_error_row_for_chat`  
- tests `test_product_surface_pcgap.py`  
