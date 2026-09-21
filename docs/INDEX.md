# AgentBus docs

## Start here

1. **CANONICAL_FILES.md** — какие файлы с Drive копировать (актуальные id)
2. **SYNC_FROM_DRIVE.md** — порядок sync
3. **PC_HANDOFF_LIVE001.md** — запуск LIVE-001 на PC
4. **OFFLINE_FREEZE.md** — что нельзя ломать
5. **PCGAP_PRODUCT_INTEGRATION_AUDIT.md** — связи Chat→DONE

## Reference

| Doc | Role |
|-----|------|
| STRUCTURE.md | дерево репо |
| CONTRACTS.md | контракты слоёв |
| LIVE_ACCEPTANCE.md | live-сценарии |
| GETTING_STARTED.md | старт |
| INSTALL_WINDOWS.md | установка |
| TROUBLESHOOTING.md | сбои |
| README.md | обзор |

## Product path

```
Chat → product_surface (context/route) → TaskService → Runtime (freeze)
                                              ↓
                                    Verify → DONE / Recovery → Chat
```
