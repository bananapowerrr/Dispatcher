# Product path (desktop-first)

Единый путь постановки задач для ПК-продукта:

```
Chat / Resend / Recipes / Web dashboard / CLI --recipe
                    ↓
              desktop_queue
           (.agentbus/desktop_queue)
                    ↓
            runtime.claim()
                    ↓
         channels/desktop/{processing,done,errors}
                    ↓
              UI poll + history
```

Phone `channels/*/incoming` — **опционально** (`phone_filebus` / `remote_filebus`).

Autopilot / sub-agents / decomposer по-прежнему пишут в file-bus каналы — это отдельный контур.

## Offline fixes (PC)

| ID | Что |
|----|-----|
| PC-04/10 | UI result text из nested `result` dict |
| PC-13 | `FileBus.ensure()` всегда создаёт `desktop` |
| PC-14 | Doctor `desktop_channel` |
| PC-15 | UI startup ensure + history summary |
| PC-16 | History details + logs `chat:N` |
| PC-17 | Resend → desktop_queue |
| PC-18 | Recipes → desktop_queue only |
| PC-19 | Web dashboard → desktop_queue only |
| PC-20 | `agentbus init` desktop tree |
| PC-21 | `--diagnose` ensure + report desktop channel |
| PC-22 | Log DONE/ERROR human summary |
| PC-23–24 | Recipes / chat recipe / Ctrl+K → pending_ids |
| PC-25 | Deferred/stuck desktop reclaim → claim desktop/incoming |

## Live (на ПК)

См. `LIVE_ACCEPTANCE.md`: worker → diff → verify → DONE.
| PC-26–28 | DEDUPED/early terminal JSON, ProjectContext ERROR, pending stale |
