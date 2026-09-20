# OFFLINE FREEZE = GREEN

**Status:** frozen until first real live on PC.

## Allowed
- Live runbook / acceptance docs
- Run logging diagnostics
- Bug triage templates
- OpenCode `AGENTS.md` context
- Safe scripts that only collect evidence

## Forbidden
- New AI features, MCP, RAG, memory, autopilot
- Runtime/FSM/Plan contract changes
- UI rewrite
- Work for the sake of commits

## Gate
```bash
bash scripts/ci_offline.sh   # must stay GREEN
```

Next human step: `docs/LIVE_RUNBOOK.md` on the machine.
