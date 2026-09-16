# FC-37 Project Intelligence (roadmap branch)

**Parallel track** after / alongside FC-32…35 — not a second brain.

Product goal: help users who **don’t know what to do next**, and give Supervisor a richer picture than TaskResult alone.

```
PROJECT
   ↓
ANALYSIS          ← «что я вижу»
   ↓
SUPERVISOR        ← «что разумно делать»
   ↓
PLAN              ← «что решили делать»
   ↓
QUEUE             ← «что выполняется»
```

## Sub-tracks

| ID | Scope |
|----|--------|
| **37A** | Project Analysis (done / gaps / risks / debt) — **quick_scan done** |
| **37B** | Development Advisor (next 3 actions, human language) |
| **37C** | Quick Scan (session start, cheap) |
| **37D** | Deep Analysis (on demand / after N tasks / before night) |
| **37E** | Periodic / event-triggered analysis |
| **37F** | Architecture Discovery (components, entrypoints, stores) |
| **37G** | Architecture Interview (few high-impact questions only) |
| **37H** | Architecture Blockers → WAITING_DECISION (FC-30) |
| **37I** | Development Opportunities (complete / harden / tests / new) |
| **37J** | Analysis → Supervisor integration (feeds LivingPlan) |

## Modes

| Mode | When |
|------|------|
| Manual | UI: «Анализ проекта» / «Что делать дальше?» |
| Session start | Quick Scan only |
| Automatic | after N tasks, many errors, plan drift, before Night Mode |

## Hard rules

1. **Audit ≠ Plan** — analysis never silently mutates LivingPlan.
2. User confirms «Добавить в план» or «Пусть Supervisor выберет».
3. Reuse existing modules only:
   - `code_intelligence`, `context*`, `task_graph`, `pev_loop`
   - `project_state`, `memory_layers`, `post_mortem`, `lesson_learner`
   - verification / git facts from runtime
4. No giant monolith — thin facade over existing intel.
5. Pro users: silent background scan, no forced Q&A.
6. Novices: blockers → DecisionQueue (FC-30) with A/B options.

## UI sketch (product, not this sprint)

```
Проект: MyApp
🟢 Состояние    🔍 Анализ    🧭 Архитектура
📋 Текущий план
▶ Следующая задача
⚠️ Нужно ваше решение (1)
```

## Relation to current line

```
FC-26…31  plan / queue / conflict / decision / policy
FC-32     smart waiting          ← in progress
FC-33…35  estimation / night / autonomous loop
FC-36     adaptive runtime       (capability scan)
FC-37     project intelligence   (advisor + interview)
```

Implement **after** FC-32 core wait gate is green; 37A/37C first (deterministic scan, no LLM required).


## Implemented

- `intelligence/project_analysis.py` — `quick_scan()`, `AnalysisReport`, opportunities → plan hints (manual).
