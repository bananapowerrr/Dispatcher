# AgentBus roadmap (current)

## Runtime engineering

| ID | Focus | Status |
|----|--------|--------|
| R1 | Terminal path (`finish_task`) | done / in repo |
| R2 | ExecutionResult → Evidence | done / in repo |
| R3 | Recovery Controller | done / in repo |
| R4 | Worker / fallback contract | done |
| R5 | Context budget | done |
| R6 | Night Mode v0 | done |

## Product distribution — UPDATE-001

| ID | Focus | Status |
|----|--------|--------|
| UPDATE-001A | Version + Release Manifest contract | done |
| UPDATE-001B | UpdateChecker (fetch + compare) | done |
| UPDATE-001C | UI / Chat notification | done |
| UPDATE-001D | External agentbus-updater process | done |
| UPDATE-001E | Hash verify + backup/replace/rollback | done |
| UPDATE-001F | GitHub Release + build pipeline | done |

### Update principles

1. **App does not replace itself while running** — external updater.
2. **User data never in the install package path** (`%APPDATA%/AgentBus/` stays).
3. **Fail-closed manifest**: missing sha256 / invalid JSON → no update offer.
4. **Git is for developers**; Releases + UpdateChecker are for users.

### Target UX

```
UpdateChecker → "AgentBus 0.10.1 available" → [Update] [Later]
  → download + verify → updater stops app → replace binaries → restart
  → failed start → rollback
```

## Live acceptance

LIVE-001 … acceptance on real PC (Ollama/Aider) — parallel, not a blocker for R4–R5 / UPDATE-001A–B.

## Explicitly not now

MCP, heavy RAG, multi-agent parallelism, cloud provider sprawl, Day-doc spam.
