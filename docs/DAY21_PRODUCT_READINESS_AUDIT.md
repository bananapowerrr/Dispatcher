# Day 21 — Product Readiness Audit (Live transition)

**Mode:** audit only — no Runtime/FSM/intake/verify/executor changes.  
**Git HEAD audited:** `a8ce1e189f52` (DEV-SYNC 2026-09-21 09:02 from drive)  
**Scope:** Chat → Task → Plan → Context → Router → Worker → Diff → Verify → DONE/ERROR → Recovery  
**Day 20 docs:** still Drive-only (404 on GitHub) — expected until next human sync.

---

## 1. Chain readiness matrix

| Layer | Offline code | Offline tests | Live evidence | Entry point(s) | Caller | Needs PC? |
|-------|--------------|---------------|---------------|----------------|--------|-----------|
| **Chat → Task** | ✅ | partial | ❌ | `ui/chat_panel.py` send path; `ui/chat_task_bridge.py` | UI user submit | Yes |
| **Task → Plan / intake** | ✅ frozen | ✅ | ❌ | `src/core/intake_pipeline.py` (`accept_task_raw`) | Runtime / file-bus | Yes |
| **Context report** | ✅ surface | ✅ day15 | ❌ | `src/intelligence/context_report.py` | optional UX / doctor | Optional first live |
| **Context in Runtime** | ✅ (rp_context) | mixed | ❌ | `src/core/rp_context.py` | Runtime execute path | Yes |
| **Router (select_executor)** | ✅ frozen | ✅ | hist. Aider | `src/core/router.py::select_executor` | `runtime.py` | Yes |
| **Router surface (plan_route)** | ✅ additive | ✅ day16 | ❌ | `src/core/worker_route.py` + `worker_route_surface.py` | doctor / chat format only — **does not replace select_executor** | After LIVE-001 |
| **Worker Aider / Ollama** | ✅ config + core | unit | hist. only | `src/core/workers.py`, `executor.py` | select_executor | **Yes — LIVE-001** |
| **Diff / git safety** | ✅ | ✅ hardening | ❌ | executor / git helpers | worker result | Yes |
| **Verify gate** | ✅ frozen | ✅ fail-closed tests | ❌ | `src/core/rp_verify.py` | Runtime phase | **Yes — critical** |
| **DONE gate** | ✅ | ✅ | ❌ | Runtime terminal + chat `notify_done` | result poll | Yes |
| **ERROR path (chat)** | ⚠️ partial | day14 tests on bridge | ❌ | `notify_error` + `error_ux.humanize_error` | chat_panel poll | Yes |
| **Recovery UX bundle** | ✅ | day12/13 | ❌ | `src/app/recovery_ux.py` | bridge (unused by panel) | After ERROR seen |
| **Recovery → Chat wire** | ⚠️ **GAP** | bridge unit | ❌ | `ui/chat_recovery_bridge.py` | **not called from chat_panel** | P0 product |
| **Replan live** | prepared docs | offline only | ❌ | plan/replan structures | Runtime on fail | After REC-001 |
| **Settings contract declare** | ✅ | day13_1 | n/a | `src/app/settings_contract.py` | tests / docs | — |
| **Settings Panel enforce RO** | ⚠️ **GAP** | tests may pass AST on Drive copy | n/a | `ui/settings_panel.py` | UI | P0 offline-safe fix |
| **Bilingual EN/RU** | ✅ ~parity | day13 | n/a | `config/strings_*.yaml` + `t()` | UI | Polish |
| **Doctor** | ✅ | ✅ | ❌ on this PC | `src/core/doctor.py` | `ci_offline.sh` | Yes |
| **Live preflight** | ✅ | day17 | ❌ | `scripts/live001_preflight.py` | human | **Yes** |
| **Fail layer classifier** | ✅ | day18 | ❌ | `src/core/live_fail_layer.py` | pack / logs | On first FAIL |
| **Evidence pack + triage** | ✅ | day19 | ❌ | `scripts/pack_run_evidence.py` | human after run | On FAIL/PASS |
| **Night mode** | docs only (Drive) | — | ❌ | — | — | After manual live cycle |
| **ci_offline gate** | ✅ | scripted | must run on PC | `scripts/ci_offline.sh` | human | **Before LIVE-001** |

Legend: ✅ present in HEAD · ⚠️ present but incomplete wire · ❌ no evidence on this machine yet

---

## 2. Gap matrix (do not fix all at once)

### P0 — blocks honest “product shell complete”

| ID | Gap | Evidence on HEAD `a8ce1e18` | Suggested action | Touches frozen core? |
|----|-----|------------------------------|------------------|----------------------|
| **P0-1** | Settings RO **not enforced** in UI | `settings_panel.py`: **0** refs to `is_editable_tab` / `_ro_banner`; still calls `set_flag` (×5), `set_active_policy` (×9), saves prompt | Apply Day 13.1 panel patch from Drive (or re-apply): RO tabs show banner + no mutation; workers/language/ui editable | **No** (UI only) |
| **P0-2** | Recovery bridge **not wired** into ERROR path | `chat_panel.py`: `format_recovery_for_chat` count **0**; path is `humanize_error` → `notify_error` → `append` | Small wire: on ERROR row, call `format_recovery_for_chat` / `merge_terminal_with_recovery` before append | **No** (UI only) |
| **P0-3** | No LIVE-001 evidence | N/A | Run Track A on PC | N/A |

### P1 — product clarity after first live

| ID | Gap | Notes |
|----|-----|-------|
| **P1-1** | Day 20 INDEX / night constraints not in Git | Drive only — sync when convenient |
| **P1-2** | `plan_route` surface not shown in doctor text by default | `diagnose.py` loads workers; route_surface optional |
| **P1-3** | Context report not in main chat “user story” | Module exists; call sites optional |
| **P1-4** | Unified run narrative (Day 25 idea) | progress_ux + error_ux + recovery not one story yet |

### P2 — later

Night mode code, multi-project, 20-task matrix, packaging.

---

## 3. Docs vs code divergence (Days 13–20)

| Doc claim | Code reality (HEAD) |
|-----------|---------------------|
| Day 13.1 Settings contract enforced | **Diverges:** contract module + tests exist; **panel still mutates** policy/flags/prompt |
| Day 14 Recovery → Chat | **Diverges:** bridge + tests exist; **chat_panel does not import bridge** |
| Day 15 Context report | Aligns: module + tests + doc present |
| Day 16 Route surface | Aligns: surface additive; `select_executor` still authority |
| Day 17–19 preflight / fail layer / pack triage | Aligns: scripts + tests present |
| Day 20 Night constraints | **Not in Git yet** (Drive) |

**Conclusion:** several Day 13–14 **artifacts landed**, but **product wiring claims are ahead of `chat_panel` / `settings_panel` behavior**. Treat P0-1 and P0-2 as contract repair, not new features.

---

## 4. Frozen core (do not touch without live fail layer)

| Component | Path | Status |
|-----------|------|--------|
| FSM / Runtime | `src/core/runtime.py` | freeze |
| Intake | `src/core/intake_pipeline.py` | freeze |
| Verify | `src/core/rp_verify.py` | freeze |
| Executor selection | `src/core/router.py::select_executor` | freeze |
| Reclaim | `src/core/reclaim.py` | freeze |
| Workers load | `src/core/workers.py` | freeze unless ENV fix |

`plan_route` / `worker_route_surface` remain **advisory**.

---

## 5. Track A — PC sequence (authoritative)

```
1. docs/SYNC_FROM_DRIVE.md   # resolve Drive vs Git duplicates
2. bash scripts/ci_offline.sh
3. doctor (critical_ok)
4. scripts/live001_preflight.py
5. LIVE-001: create test_aider.txt "Aider pipeline OK"
6. On FAIL → live_fail_layer.classify_* → fix ONLY that layer
7. pack_run_evidence.py → archive
8. LIVE-001 retry
```

Historical LIVE-001 prompt — **do not change**:

> Создай test_aider.txt с одной строкой: Aider pipeline OK

---

## 6. Track B — safe parallel work (only if PC blocked)

Allowed offline **without** expanding roadmap:

1. **P0-1** Settings panel RO enforcement (UI)
2. **P0-2** One-file ERROR path → recovery bridge (UI)
3. Bilingual keys already on Drive
4. Keep docs/index accurate

Forbidden offline: night scheduler code, new workers, RAG/MCP, FSM edits, replacing `select_executor`.

---

## 7. Decision

| Question | Answer |
|----------|--------|
| Offline shell architecture? | **Yes** — enough surface around freeze |
| Product shell **behavior** complete? | **No** — P0-1, P0-2 |
| Next highest value? | **PC LIVE-001** OR offline UI-only P0-1/P0-2 |
| More offline Day 22 feature batches? | **No** until live evidence |

Phase change stands:

> offline development gate closed for *features*;  
> system must now be **proven** Chat → DONE on real PC.
