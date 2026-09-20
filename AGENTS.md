# Agent instructions (OpenCode / local coding agents)

You are working on **AgentBus / NVCode** — a local AI coding orchestrator.

## Source of truth
- **GitHub repo** after sync — not Drive parallel edits.
- Architecture: `docs/CONTRACTS.md`, `docs/AUDIT_MAIN_0.10.md`, `docs/FINISH_5DAYS.md`

## Hard rules
1. **LLM proposes; Runtime + Verification decide DONE.** Never mark DONE without verify.
2. Do **not** rewrite FSM, DONE gate, Plan terminal authority, or intake fail-closed contracts.
3. Do **not** add MCP, RAG, parallel workers, autopilot, or UI redesign unless the human explicitly asks.
4. Prefer **minimal diffs** + targeted tests.

## Offline gate (must stay green)
```bash
bash scripts/ci_offline.sh
```

## Live workflow
1. Read `docs/LIVE_RUNBOOK.md`
2. Run scenario from `docs/LIVE_ACCEPTANCE_SUITE.md`
3. On failure: fill `docs/templates/LIVE_BUG.md` using `.agentbus/runs/<id>/`
4. Fix **one** bug category → re-run same LIVE-XXX → commit

## Where code lives
- Runtime: `src/core/`
- Intelligence (proposes only): `src/intelligence/`
- App API for UI: `src/app/`
- UI: `ui/`
- Safety: `src/safety/`

## Forbidden without explicit request
New AI features, memory systems, large refactors, renaming core modules, "cleanup for cleanup".
