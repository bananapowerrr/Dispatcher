# NVCode / NVC — Architecture (2026-09)

## Product

**NVCode (NVC)** — local AI IDE for developers.  
Internal orchestration runtime remains **AgentBus** (do not mass-rename modules yet).

Formula: **IDE model + agent + dispatcher + change control**.

## Layers

```
NVCode UI
   ↓
Application API (src/app/)
   ↓
Runtime/Core  |  Intelligence
   ↓
Workers / Providers / LLM
```

Rules:
- UI must not import living_plan / decision_queue / supervisor directly.
- Intelligence proposes; Runtime decides.
- LLM is not source of truth.

## Work context

Project → File → Selection → Conversation → Task → Changes → Verification

## Workspace modes (FC-45)

| Mode | Focus |
|------|--------|
| Code | Explorer, Editor, Changes, Diff |
| Agent | Chat, Queue, Task, Trace |
| Project | Health, Plan, Audit, Decisions |
| Full | Everything (advanced) |

Progressive disclosure: beginner starts in **Agent**.

## Upcoming

- Navigation history (Back/Forward)
- ChangeSet + Safe Undo/Redo (separate from nav)
- Capability profiles (Economy/Standard/Power)
- Interactive Project Health (FC-48)

## Status

FC-38…FC-44 done. FC-45 in progress.
