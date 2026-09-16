# Architecture Inventory — NVCode / AgentBus

**Date:** 2026-09-17  
**Scope:** full repository audit (no mass deletion in this pass)  
**Product:** NVCode (NVC) · **Runtime name in code:** AgentBus  

## Purpose

Inventory of what is **canonical**, **optional**, **historical**, or **needs verification**.  
Goal is clarity for the next human/AI developer — **not** minimizing file count.

**Intentional splits** (e.g. `runtime_process` → `rp_*` mixins) are **KEEP**: they exist so a failure or edit in one stage does not require rewriting a 2k-line monolith, and so tooling can edit bounded files.

---

## Current architecture (canonical)

```
NVCode UI (ui/)
    ↓
Application API (src/app/)
    ↓
┌──────────────────┬────────────────────┐
│ Core / Runtime   │ Intelligence       │
│ src/core/        │ src/intelligence/  │
└────────┬─────────┴─────────┬──────────┘
         ↓                   ↓
   Workers/Executor     Advisors/Plan
         ↓
   Providers / Models
```

**Principle:** Intelligence proposes → Runtime decides → Verification gates DONE.

**UI should prefer** `src/app/*Service` over direct imports of `living_plan`, `decision_queue`, etc.

---

## Repository scale (approx.)

| Area | Scale |
|------|------:|
| Python under `src/` | ~180 modules |
| UI panels | ~35 |
| Tests | ~153 files |
| Docs | ~46 markdown |
| Scripts | ~15 |
| Total tracked-ish files (py/md/yaml/…) | ~480 |

---

## Classification legend

| Tag | Meaning |
|-----|---------|
| **CORE** | Required for dispatcher/runtime |
| **PRODUCT** | User-facing product behavior |
| **OPTIONAL** | Feature-flag / soft-fail; runtime survives without it |
| **TEST INFRA** | Offline/live harness |
| **HISTORICAL** | Docs or leftovers; do not treat as current design |
| **NEEDS VERIFICATION** | Unclear static usage — do not delete yet |
| **DELETE CANDIDATE** | High confidence unused *or* pure re-export dead end |

Actions: **KEEP** · **KEEP/OPTIONAL** · **MERGE CANDIDATE** · **ARCHIVE** · **DELETE CANDIDATE** · **NEEDS VERIFICATION**

---

## 1. Entrypoints

| File | Category | Status | Responsibility | Notes |
|------|----------|--------|----------------|-------|
| `dispatcher.py` | CORE | KEEP | Thin CLI → `dispatcher_main` | Canonical process entry |
| `dispatcher_ui.py` | PRODUCT | KEEP | UI entry | |
| `admin_ui.py` | OPTIONAL | KEEP | Admin flags UI | Separate process |
| `start.sh` / `start.bat` / `start_ui.bat` | PRODUCT | KEEP | Launch helpers | |
| `start_doctor.bat` | PRODUCT | KEEP | Doctor shortcut | |

---

## 2. Core runtime split (intentional — KEEP)

| Module | Responsibility | Used by | Action |
|--------|----------------|---------|--------|
| `runtime.py` | Orchestrator, poll loop, graceful stages | entry / tests | **KEEP** |
| `runtime_daemon.py` | Daemon wiring / long-run helpers | runtime path | **KEEP** |
| `runtime_process.py` | Composes `RP*` mixins into `RuntimeProcess` | `runtime.py` | **KEEP** (facade) |
| `runtime_ops.py` | Claim / lease / git / verify helpers | `runtime.py` | **KEEP** |
| `runtime_ops_claim.py` | Claim split | ops | **KEEP** (size split) |
| `runtime_ops_git.py` | Git ops split | ops | **KEEP** (size split) |
| `rp_lifecycle.py` | Lifecycle stage mixin | `runtime_process` | **KEEP** |
| `rp_lifecycle_stages.py` | Stage table / transitions | lifecycle | **KEEP** |
| `rp_lifecycle_learn.py` | Post-task learn hooks | lifecycle | **KEEP/OPTIONAL** |
| `rp_context.py` | Context stage | process | **KEEP** |
| `rp_context_budget.py` | Context budget | context | **KEEP** |
| `rp_context_memory.py` | Memory injection | context | **KEEP** |
| `rp_cache_skills.py` | Cache + skills stage | process | **KEEP** |
| `rp_cache.py` | Cache helpers | cache stage | **KEEP** |
| `rp_skills_stage.py` | Skills execution stage | process | **KEEP** |
| `rp_llm.py` | LLM/worker stage | process | **KEEP** |
| `rp_verify.py` | Verify stage | process | **KEEP** |
| `pipeline_stages.py` | Pure stage helpers | runtime, lifecycle, smoke | **KEEP** |
| `stage_guard.py` | Per-stage try/guard | many `rp_*` | **KEEP** |

**Verdict:** Not historical fragmentation. Do **not** merge solely to reduce file count.  
**REVIEW only if** cyclic imports or double pipeline implementations appear (none found as competing pipelines).

---

## 3. Task / queue / bus (CORE)

| Module | Status | Responsibility |
|--------|--------|----------------|
| `bus.py` | KEEP | File-bus atomic moves |
| `local_queue.py` | KEEP | Desktop chat queue |
| `tasks.py` | KEEP | Task model / FSM constants |
| `task_contract.py` | KEEP | Intake validation |
| `task_result.py` | KEEP | Unified TaskResult / history cards |
| `task_service.py` | KEEP | Submit API for UI/CLI |
| `task_safety.py` | KEEP | Safety around tasks |
| `intake_pipeline.py` | KEEP | Normalize intake |
| `reclaim.py` | KEEP | Stuck processing reclaim |
| `dedupe.py` | KEEP | Task dedupe |
| `policy.py` | KEEP | Runtime policy |
| `dispatcher_lock.py` | KEEP | Single dispatcher lock |
| `dispatcher_main.py` | KEEP | Main loop bootstrap |
| `preflight.py` | KEEP | Preflight checks |
| `config.py` | KEEP | Paths, env, channels |
| `feature_flags.py` | KEEP | Feature flags |
| `errors.py` / `error_ux.py` | KEEP | Errors + human messages |
| `logger.py` | KEEP | Logging |
| `project.py` | KEEP | Project resolution helpers |
| `repair.py` | KEEP | Repair hooks |
| `doctor.py` | KEEP | Environment doctor |
| `configuration_advisor.py` | KEEP | First-run / capability advice |

---

## 4. Worker selection stack (multiple layers — document, don’t merge blindly)

```
capability_scan  →  what models/tools exist
model_profiles   →  profile metadata (context, backend kind)
capability_router→  plugin/capability hints on task
router + router_score + ranking → pick worker for task
dynamicpool      →  dynamic worker pool (narrow use)
backend / native_backend / fallback → execution adapters
```

| Module | Status | Notes |
|--------|--------|-------|
| `router.py` | KEEP | Primary worker selection |
| `router_score.py` | KEEP | Scoring helper for router |
| `ranking.py` | KEEP | Adaptive ranking / history |
| `capability_scan.py` | KEEP | FC-36 hardware/model discovery |
| `capability_router.py` | KEEP | Plugin capability enrichment (UI chat uses it) |
| `model_profiles.py` | KEEP | Profiles for backends |
| `dynamicpool.py` | KEEP/OPTIONAL | Few call sites (`rp_skills_stage`) — still live |
| `backend.py` | KEEP | Backend abstraction entry |
| `native_backend.py` | KEEP | OpenAI-compatible / local tools path |
| `fallback.py` | KEEP | Fallback when primary backend fails |
| `workers.py` / `worker_api.py` | KEEP | Worker registry / API |
| `executor.py` | KEEP | Subprocess execution contract |
| `tool_registry.py` | KEEP | Tools for workers |
| `skill_worker.py` | KEEP | Skill-as-worker bridge |

**Not duplicates of one function** — layered. Document boundaries; only merge if two files implement the *same* selection algorithm.

---

## 5. Verification (CORE)

| Module | Status | Notes |
|--------|--------|-------|
| `verification_engine.py` | KEEP | Ladder / engine |
| `verify_policy.py` | KEEP | Policy levels (widely referenced) |
| `verify.py` | KEEP | Lower-level verify helpers |
| `static_guard` (safety) | KEEP | AST/static gate |

---

## 6. Test / E2E infrastructure

| Module | Status | Role |
|--------|--------|------|
| `e2e_harness.py` | KEEP | Offline E2E harness |
| `pipeline_e2e.py` | KEEP | Pipeline matrix runner |
| `mock_worker.py` | KEEP | Deterministic worker mock |
| `harness_registry.py` | KEEP | Register harnesses; UI setup wizard refs |
| `scripts/smoke_offline.py` | KEEP | Canonical offline smoke |
| `scripts/live_smoke.py` | KEEP | Live path (PC) |
| `scripts/benchmark_harness.py` | KEEP | Benchmark, not unit tests |
| `scripts/regression_fc22.sh` | KEEP | Regression script |

No evidence of a second competing E2E stack that should be deleted.  
**Do not delete** rarely run harnesses without checking CI/docs.

---

## 7. Application API (`src/app/`) — PRODUCT

| Module | Status | Responsibility |
|--------|--------|----------------|
| `project_service.py` | KEEP | Snapshot, audit, workspace summary |
| `tasks_service.py` | KEEP | Queue buckets, task detail, decisions façade |
| `files_service.py` | KEEP | Safe read/write/tree |
| `agent_service.py` | KEEP | Editor context → prompt enrich |
| `changes_service.py` | KEEP | Git change list / diff text |
| `workspace_mode.py` | KEEP | FC-45 Code/Agent/Project/Full |
| `nav_history.py` | KEEP | Back/Forward navigation (not ChangeSet undo) |

**UI dependency rule:** prefer these façades. Direct `intelligence.*` from UI is tech debt (e.g. some panels still call snapshot/audit directly — acceptable short-term if behind panel, migrate gradually).

---

## 8. Intelligence (`src/intelligence/`)

### Product / active chain

```
project_state / project_snapshot
        ↓
project_analysis / project_audit / development_advisor
        ↓
architecture_* + decision_queue + blockers
        ↓
living_plan → dynamic_queue
        ↓
autopilot_policy / smart_waiting / estimation / night_scheduler
        ↓
autonomous_loop (optional)
        ↓
Runtime (core)
```

| Module | Category | Status | Notes |
|--------|----------|--------|-------|
| `project_snapshot.py` | PRODUCT | KEEP | UI Project Center |
| `project_audit.py` | PRODUCT | KEEP | Audit text/dict |
| `project_analysis.py` | PRODUCT | KEEP | Analysis engine |
| `development_advisor.py` | PRODUCT | KEEP | Next steps + plan draft |
| `project_state.py` | PRODUCT | KEEP | Persisted project state |
| `project_index.py` | PRODUCT | KEEP | Index for analysis |
| `living_plan.py` | PRODUCT | KEEP | Plan model |
| `dynamic_queue.py` | PRODUCT | KEEP | Plan → queue emission |
| `decision_queue.py` | PRODUCT | KEEP | Human decisions |
| `architecture_discovery.py` | PRODUCT | KEEP | |
| `architecture_interview.py` | PRODUCT | KEEP | |
| `architecture_blockers.py` | PRODUCT | KEEP | |
| `session_bootstrap.py` | PRODUCT | KEEP | Session banner |
| `session_memory.py` | PRODUCT | KEEP | MEMORY.md-style |
| `context_intake.py` | PRODUCT | KEEP | Message classification |
| `context.py` / `context_budget.py` / `context_planner.py` | CORE/PRODUCT | KEEP | Context build |
| `conversation.py` | PRODUCT | KEEP | Multi-turn |
| `autopilot_policy.py` | OPTIONAL | KEEP | Policy for autonomy |
| `smart_waiting.py` | OPTIONAL | KEEP | When not to emit |
| `estimation.py` | OPTIONAL | KEEP | Effort estimates |
| `night_scheduler.py` | OPTIONAL | KEEP | Night deferral |
| `autonomous_loop.py` | OPTIONAL | KEEP | Loop supervisor |
| `supervisor_roles.py` | OPTIONAL | KEEP | Role prompts |
| `conflict.py` | OPTIONAL | KEEP | Conflict detection |
| `attachments.py` | PRODUCT | KEEP | Chat attachments |
| `solution_cache.py` | OPTIONAL | KEEP | Cache hits (feature flag) |
| `semantic_memory.py` | OPTIONAL | KEEP | Similar tasks |
| `codebase_rag.py` | OPTIONAL | KEEP | Lexical RAG |
| `code_intelligence.py` | OPTIONAL | KEEP | Graph/intel |
| `pev_loop.py` | OPTIONAL | KEEP | PEV planning (still referenced from rp_*) |
| `sub_agent.py` | OPTIONAL | KEEP | Subtasks (feature flag) |
| `lesson_learner.py` | OPTIONAL | KEEP | Lessons |
| `presets.py` | PRODUCT | KEEP | Behavior presets |
| `report.py` | OPTIONAL | KEEP | Reports (many string hits — verify before delete) |
| `post_mortem.py` | OPTIONAL | KEEP | Failure analysis |
| `memory_layers.py` | OPTIONAL | KEEP | Memory layering |
| `task_graph.py` | OPTIONAL | KEEP | Graph of tasks |
| `chat_parser.py` | NEEDS VERIFICATION | Few refs | Inspect before delete |
| `cfg_builder.py` | DELETE CANDIDATE / NEEDS VERIFICATION | **0 static refs** outside self | Confirm no dynamic import |
| `plugin` path N/A | — | — | plugins live under `plugins/` |

**No second parallel “planner product”** found beyond living_plan + dynamic_queue + autonomous_loop (loop is optional automation on top of plan).

---

## 9. Safety (`src/safety/`)

| Module | Status | Role |
|--------|--------|------|
| `gitops.py` | KEEP | Git operations |
| `diff_engine.py` / `diff_policy.py` | KEEP | Pending diffs apply/reject |
| `project_lock.py` | KEEP | Per-project lock |
| `security.py` | KEEP | Path sandbox etc. |
| `health.py` | KEEP | Provider health |
| `loopguard.py` | KEEP | Loop detection |
| `file_sentinel.py` / `file_watcher.py` | KEEP/OPTIONAL | Hygiene / watch |
| `syntax_guard.py` / `static_guard.py` | KEEP | Static gates |
| `skill_sandbox.py` | KEEP/OPTIONAL | Skill isolation |
| `language_guard.py` | OPTIONAL | Language bias guard |
| `hooks.py` | OPTIONAL | Pre/post hooks |
| `worktree.py` | OPTIONAL | Worktree isolation (future parallel) |

---

## 10. Skills (`src/skills/`)

| Module | Status | Notes |
|--------|--------|-------|
| `skills.py` | KEEP | Main SkillRegistry implementation |
| `registry.py` | KEEP | Thin re-export of `skills.skills` — **not dead**, convenience API |
| `tools.py` | KEEP | ToolRegistry |
| `matcher.py` | KEEP | Match helpers |
| `builtin/*` | KEEP | Builtin skill packs |
| `meta_classifier.py` | KEEP | Meta classification |
| `task_classifier.py` | KEEP | Shared classification |
| `classifiers.py` | NEEDS VERIFICATION | Low refs |
| `skill_learner.py` | OPTIONAL | Propose new skills |
| `custom_loader.py` | OPTIONAL | Custom skills |
| `refactorer.py` | OPTIONAL | Programmatic refactor |
| `task_decomposer.py` | OPTIONAL | Decompose tasks |
| `task_grouper.py` | OPTIONAL | Group tasks |
| `test_runner.py` | OPTIONAL | Test runs from skills |
| `metrics.py` | KEEP | Bridge to `utils.metrics` (may look unused by import count if only internal) |
| `autopilot.py` | OPTIONAL | Skill-side autopilot helpers |

---

## 11. Utils (`src/utils/`)

| Module | Status | Notes |
|--------|--------|-------|
| `task_trace.py` | KEEP | Trace lifecycle |
| `metrics.py` | KEEP | Global metrics |
| `i18n.py` | KEEP | Strings |
| `diagnose.py` | KEEP | Diagnose helpers |
| `pipeline_events.py` | KEEP | Event emission |
| `budget.py` / `cost_tracker.py` | KEEP/OPTIONAL | Economics |
| `explainability.py` | OPTIONAL | Why-decision |
| `structured_output.py` | OPTIONAL | JSON repair |
| `slash_commands.py` | PRODUCT | Chat slash |
| `status_board.py` | OPTIONAL | Console board |
| `smoke.py` | TEST INFRA | Smoke helpers |
| `performance.py` | OPTIONAL | Timing |
| `log_archive.py` | OPTIONAL | Log TTL/archive |
| `stream.py` | KEEP | Stream helpers (many refs) |
| `alerts.py` | OPTIONAL | Alerts |
| `updater.py` | DELETE CANDIDATE / NEEDS VERIFICATION | **0 static refs** |
| `utils.py` | KEEP | Misc helpers |

---

## 12. UI (`ui/`)

### Canonical product surface

| Panel / module | Status | Role |
|----------------|--------|------|
| `main_window.py` | KEEP | Shell, FC-44/45 wiring |
| `chat_panel.py` | KEEP | Primary intake |
| `editor_panel.py` | KEEP | Tabs editor |
| `explorer_panel.py` | KEEP | File tree |
| `queue_panel.py` | KEEP | Operational center |
| `task_detail_panel.py` | KEEP | Trace card |
| `diff_panel.py` / `changes_panel.py` | KEEP | Change control UI |
| `project_center_panel.py` | KEEP | Project workspace |
| `projects_panel.py` | KEEP | Project picker |
| `setup_wizard.py` | KEEP | Onboarding |
| `settings_panel.py` | KEEP | Settings |
| `history_panel.py` / `logs_panel.py` | KEEP | Observability |
| `command_palette.py` / `commands.py` | KEEP | Palette |
| `theme.py` / `i18n_ui.py` / `paths.py` / `notify.py` | KEEP | Chrome |
| `status_labels.py` / `result_text.py` / `last_outcome.py` | KEEP | Labels |
| `async_poll.py` | KEEP | BG poll |
| `dispatcher_ctl.py` | KEEP | Start/stop dispatcher |
| `tray_manager.py` | OPTIONAL | Tray |
| `workers_panel.py` / `skills_panel.py` / `metrics_panel.py` | KEEP/OPTIONAL | Advanced |
| `recipes_panel.py` / `extensions_panel.py` | OPTIONAL | Power features |
| `phone_bus_panel.py` | OPTIONAL | Phone file-bus companion |
| `pev_panel.py` / `sentinel_panel.py` | OPTIONAL | Advanced/ops |
| `admin_window.py` | OPTIONAL | Admin |
| `help_dialog.py` | KEEP | Help |

**Progressive disclosure (FC-45):** default mode `agent`; `full` exposes advanced tabs. Do not delete advanced panels — hide them.

---

## 13. CLI / plugins / config / eventbus / providers

| Area | Status | Notes |
|------|--------|-------|
| `src/cli/init_wizard.py` | KEEP | CLI init |
| `src/cli/recipes.py` | KEEP | Recipes CLI |
| `src/cli/dashboard_server.py` | OPTIONAL | Few refs — keep until product decision |
| `plugins/` | KEEP | Extension points |
| `config/` | KEEP | providers, workers, flags, strings, presets |
| `eventbus/` | KEEP | Events |
| `providers/` | KEEP | Provider adapters |
| `recipes/` | KEEP | Task recipes |
| `channels/` | KEEP | File-bus directories (runtime data, not source) |

---

## 14. Documentation

### CURRENT (source of truth)

| Doc | Role |
|-----|------|
| `NVCODE_ARCHITECTURE.md` | Product + layer rules |
| `STRUCTURE.md` | Layout |
| `LAUNCH.md` / `INSTALL_WINDOWS.md` / `ONBOARDING_RU.md` | Ops |
| `FEATURE_FLAGS.md` | Flags |
| `TROUBLESHOOTING.md` | Ops |
| `UI.md` / `FC44_UI_WORKFLOW.md` | UI contract |
| `API.md` | API (verify freshness periodically) |
| `SKILLS.md` / `PLUGIN_SDK.md` | Extensibility |
| `CHANNELS_RU.md` | Phone bus |
| `CI.md` / `EXECUTOR.md` | Engineering |
| `ARCHITECTURE_INVENTORY.md` | **This file** |
| `INDEX.md` | Doc index — update links |

### HISTORICAL (do not use as current architecture)

Mark or move later to `docs/archive/`:

- `AUDIT_*`, `HANDOFF_*`, `FIX_PLAN.md`, `SYNC_STATUS.md`, `STATUS_OFFLINE.md`
- Most `FC2x`–`FC3x` narrative docs after features landed (keep as history, not instructions)
- `PRODUCT_BACKLOG_append.md` if superseded by live backlog

**Risk:** An agent may re-implement deleted designs from old FC docs.  
**Action:** header banner:

```markdown
> HISTORICAL — DO NOT USE AS CURRENT ARCHITECTURE. See NVCODE_ARCHITECTURE.md
```

### No `AgentBus_canonical.tgz` found in this working tree

If it appears on Drive/Dropbox copies, treat as **ARCHIVE outside git**.

---

## 15. Safe cleanup lists (for a *later* task — not executed here)

### Safe cleanup (high confidence after second verification pass)

1. Add HISTORICAL banners to old audit/handoff docs (or move to `docs/archive/`).
2. Confirm `cfg_builder.py` and `updater.py` have no dynamic imports → then DELETE or ARCHIVE.
3. Deduplicate root vs `scripts/` launch bat files if identical (`start_doctor.bat` appears both places — compare hashes).
4. Ensure `workers_state.json` is gitignored if runtime state (currently in root).

### Refactor candidates (architecture decision required)

1. UI panels still importing `intelligence.*` directly → route via `ProjectService` / `TasksService`.
2. Dual metrics entry (`skills.metrics` vs `utils.metrics`) — keep bridge, document single sink.
3. `verify` vs `verification_engine` vs `verify_policy` naming clarity in docs only.
4. FC-45 progressive tab *hiding* (not deletion) for Logs/Metrics/PEV/Sentinel/Phone in non-full modes.

### Do not touch

- Entire `rp_*` / `runtime_*` split  
- FSM / DONE gate / intake security / executor timeouts  
- File-bus atomicity  
- Application API façades  
- Offline smoke + e2e harness  
- Verification ladder  

---

## 16. Duplicate mechanisms — summary answers

| Question | Answer |
|----------|--------|
| How many worker/model selectors? | **Layered**, not clones: scan → profiles → router/score/ranking → backend/fallback |
| Competing runtimes? | **No** — single `Runtime` + process mixins |
| Competing planners? | **living_plan + dynamic_queue**; `autonomous_loop` optional automation |
| Competing verifiers? | **One ladder** (`verification_engine` + policy); `verify.py` helpers |
| Skills entry? | **`skills.skills`** canonical; `registry.py` re-export |
| App API present? | **Yes** (`src/app`); migrate remaining UI direct imports gradually |

---

## 17. Success criterion (this audit)

A later developer/agent can see:

1. **Canonical path** UI → app → core/intelligence → workers  
2. **Why many small core files exist** (intentional stage isolation)  
3. **What not to resurrect** from HISTORICAL docs  
4. **What not to delete** without verification (`cfg_builder`, harnesses, optional intelligence)  

**File count is not a KPI.** Reducing competing *ideas* and dead *instructions* is.

---

## 18. Recommended next work (ordered)

1. Banner or archive HISTORICAL docs (low risk).  
2. FC-45A Agent Behavior settings in `ui.yaml` (product UX) — per latest plan.  
3. Dynamic import grep CI for DELETE CANDIDATES before removal.  
4. ChangeSet / Safe Undo design (new product surface — not cleanup).  
5. Capability profiles (Economy/Standard/Power) — adapt limits, not safety.

---

*Generated as audit-only pass. No modules deleted in this change set.*

---

## Cleanup log (2026-09-17)

Controlled cleanup (no runtime changes):

1. **Docs:** 30 historical FC/audit/handoff files moved to `docs/archive/` with HISTORICAL banner.
2. **CURRENT docs** left in `docs/` (see INDEX.md).
3. **`cfg_builder.py` / `updater.py`:** zero static refs → moved to `src/_archive_candidates/` (not deleted).
4. **`workers_state.json`:** already in `.gitignore`.
5. **`start_*.bat`:** root vs `scripts/` differ (not identical) — kept both; root is user entrypoint.

Runtime / `rp_*` / FSM / verify / intake **untouched**.
