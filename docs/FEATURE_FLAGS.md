# Feature flags

Файл: `config/feature_flags.yaml`  
Env: `AGENTBUS_FEATURE_<NAME>=0|1`

## Важные флаги

| Флаг | По умолчанию | Смысл |
|------|:---:|--------|
| `phone_filebus` / `remote_filebus` | false | Очередь `channels/` с телефона |
| `skills` | true | Детерминированные навыки |
| `solution_cache` | true | Кэш решений |
| `conversation` | true | Память диалога |
| `codebase_rag` | true | Поиск по коду |
| `autopilot` | true | Генерация задач |
| `verify_policy` | true | Лестница verify |

Админка: `python admin_ui.py` или UI → настройки.
