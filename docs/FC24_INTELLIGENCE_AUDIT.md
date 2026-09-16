# FC-24 — Intelligence → Supervisor role map

**Date:** 2026-09-16  
**Rule:** reuse existing modules; do **not** spawn a parallel agent stack.

## Target Supervisor (logical roles of one meta-model, not 6 processes)

```
Supervisor (meta 1.5B / heuristics)
├── Planner      → what to do next
├── Estimator    → time / complexity
├── Prioritizer  → order / night slot
├── Reviewer     → lessons / post-mortem
├── Decision     → ALLOW / DENY / ASK (policy boundary)
└── Replanner    → SUPERSEDED / CANCELLED / PLAN vN
```

Runtime / Policy remains the only authority that **executes**.

---

## Module inventory → role

| Module | LOC | Role(s) | Reuse for Supervisor | Status |
|--------|----:|---------|----------------------|--------|
| `pev_loop.py` | 269 | **Planner** | `Plan`, `PlanStep`, `heuristic_plan`, `make_plan`, `write_plan` | ✅ core |
| `task_graph.py` | 157 | **Planner** / queue feed | `TaskGraph`, `GraphNode`, deps, `emit_ready_to_bus` | ✅ core |
| `night_scheduler.py` | 224 | **Prioritizer** | when to run heavy work, morning report | ✅ |
| `report.py` | 54 | **Prioritizer** / UX | nightly summary | ✅ thin |
| `lesson_learner.py` | 236 | **Reviewer** | failure patterns → warnings | ✅ |
| `post_mortem.py` | 132 | **Reviewer** | quarantine lessons (no MEMORY poison) | ✅ |
| `session_memory.py` | 254 | **State** | `.agentbus/MEMORY.md` rolling facts | ✅ |
| `memory_layers.py` | 133 | **State** | session / project / global bundle | ✅ |
| `semantic_memory.py` | 188 | **Context** | similar past **tasks** | ✅ |
| `solution_cache.py` | 468 | **Cache** | DONE reuse | ✅ (runtime) |
| `context.py` | 189 | **Context** | project map + file pick | ✅ |
| `context_budget.py` | 236 | **Context** | 7B slot assembly | ✅ |
| `context_planner.py` | 116 | **Context** | unified budget plan | ✅ skeleton |
| `codebase_rag.py` | 266 | **Context** | similar **code** | ✅ |
| `project_index.py` | 255 | **Context** | structural index | ✅ |
| `code_intelligence.py` | 383 | **Context** | call graph / impact | ✅ |
| `cfg_builder.py` | 147 | **Context** | CFG / impact | ✅ |
| `conversation.py` | 333 | **Context** | multi-turn session | ✅ |
| `chat_parser.py` | 41 | **Intake** | `@file` mentions | ✅ |
| `attachments.py` | 293 | **Intake** | files / OCR text | ✅ |
| `sub_agent.py` | 352 | **Execution** | child tasks (capped) | ✅ (not supervisor) |
| `presets.py` | 101 | **Policy helper** | worker preset filter | ✅ |

---

## Gaps (needed for FC-25…31, still offline-design)

| Gap | Role | Notes |
|-----|------|-------|
| **ProjectState** | State | Single serializable snapshot: goal, phase, plan_version, pending/done, constraints, risks | → **FC-25** |
| **Living Plan** statuses | Replanner | `SUPERSEDED` / `OBSOLETE` / `REPLACED` on future nodes only | → **FC-26** |
| **Plan as source of truth** | Planner | Queue derived from plan, not inverse | → **FC-27** |
| **Context Intake classifier** | Intake | COMMAND / INFO / CONSTRAINT / … | → **FC-28** |
| **Conflict record** | Decision | structured CONFLICT + affected task ids | → **FC-29** |
| **WAITING_DECISION** | Decision | human queue + risk tier | → **FC-30** |
| **Recommendation ≠ execute** | Decision | Supervisor recommends; Policy allows | → **FC-31** |
| **Estimator stats** | Estimator | P50/P80 from TaskResult history (no ML) | → **FC-33** |

---

## What NOT to rebuild

- Do not replace `pev_loop.Plan` with a second plan format — **extend** it (version, status per step).
- Do not replace `TaskGraph` — mark nodes SUPERSEDED instead of deleting history.
- Do not put execution inside Supervisor — only emit recommendations / plan diffs / questions.
- Do not require LLM for ProjectState load/save — pure JSON under `.agentbus/`.

---

## Recommended wire order (offline)

```
FC-25 ProjectState (JSON)     ← next code
FC-26 Living Plan statuses    extends pev_loop / task_graph
FC-27 Plan → eligible → queue
FC-28 Intake kinds (heuristics first)
FC-29 Conflict dataclass
FC-30 WAITING_DECISION + Task FSM hook (docs + enum)
FC-31 Policy gate on recommendations
```

## Existing runtime touchpoints (do not break)

- Skills / cache / verify / DONE gate stay in **core**
- Intelligence modules are **optional** via feature flags where already gated (`pev_enabled`, RAG, etc.)
