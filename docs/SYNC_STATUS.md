# Sync status

| Копия | Роль | Актуальность |
|-------|------|--------------|
| **Google Drive** | источник истины (разработка) | **актуальная** |
| Dropbox `/AgentBus` | зеркало для GPT / бэкап | **отстаёт** (часть core от 11.09) |

## Что уже новее на Drive, чем Dropbox

- `src/core/task_contract.py` — security validate_paths/commands
- `src/core/tasks.py` — **Task.from_dict** fail-closed security на всех intake
- `src/core/executor.py` / `reclaim.py` — soft_log
- modular `runtime_ops_*`, `rp_*` splits
- `scripts/smoke_offline.py`, `live_smoke.py`, `ci_smoke.sh`
- docs: LAUNCH, STATUS_OFFLINE, FIX_PLAN, API

## Как обновить Dropbox (на машине или вручную)

1. Скачать с Drive: `AgentBus_canonical.tgz` (в docs или корень папки AgentBus)
2. Распаковать поверх `/AgentBus` **или** заменить целиком
3. Либо: синхронизировать папку Drive → Dropbox клиентом

Коннектор Dropbox здесь **только читает** (list/metadata), **upload write недоступен** — заливка с этой среды на Dropbox невозможна.

## Правило

> Пока offline: правим Drive. Dropbox обновляем пачкой перед/после live-beta.
