# Sync status: Google Drive ↔ Dropbox

**Источник истины:** Google Drive `/AgentBus` + локальная рабочая копия разработки.

**Dropbox `/AgentBus`:** копия для GPT / запасной канал. Должна повторять структуру Drive.

## Каноническая структура корня

```
AgentBus/
├── dispatcher.py
├── dispatcher_ui.py
├── admin_ui.py
├── README.md
├── pyproject.toml          # version 0.9.1
├── pytest.ini
├── requirements.txt
├── requirements-ui.txt
├── config/
├── src/{core,intelligence,skills,safety,utils,cli}/
├── ui/
├── tests/
├── scripts/
├── docs/
├── channels/
├── eventbus/
├── providers/
├── plugins/
└── recipes/
```

**Не в корне:** `beginner_ru.yaml` (только `config/presets/` + `config/feature_presets.yaml`).

## Полный снимок

`AgentBus_canonical.tgz` в корне Drive — актуальный архив дерева (без `__pycache__`, `.agentbus`).

## Как выровнять Dropbox

1. Скачать `AgentBus_canonical.tgz` с Drive.
2. Распаковать поверх `/AgentBus` (или в чистую папку и заменить).
3. Удалить корневой `beginner_ru.yaml`, если остался.
4. Не коммитить `__pycache__` / `.pytest_cache`.

## После синхронизации

Оба канала должны иметь одинаковые:
- `src/core/{executor,feature_flags,dispatcher_main,runtime,pipeline_e2e,reclaim}.py`
- `src/skills/builtin/`
- `docs/{FIX_PLAN,SKILLS,STATUS_OFFLINE,EXECUTOR,SYNC_STATUS}.md`
- `tests/test_{executor_hardening,task_trace_terminal,pipeline_e2e_matrix,reclaim}.py`
