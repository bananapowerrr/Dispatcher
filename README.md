# AgentBus Dispatcher v1.0

Диспетчер задач для Prediction-Analyzer и других реп.

## Запуск

```powershell
cd "G:\Мой диск\AgentBus"
py -3.12 dispatcher.py
```

В `.env`:
```
SUPABASE_URL=https://....supabase.co
SUPABASE_SERVICE_ROLE_KEY=...
```

## Каналы

`channels/gpt/` — основная шина (GPT через Supabase)  
`channels/grok/`, `channels/gemini/` — запасные

Каждый канал: `incoming` `processing` `done` `errors` `deferred` `logs`

## Rate-limit OpenCode

При 429 не перебирает модели. Пишет таймер, откладывает задачи, Supabase → PENDING.

## Задача из GPT (Supabase)

Таблица `agentbus_tasks`, claim через RPC. В логах:
`Supabase CLAIMED id=...` и файл `channels/gpt/logs/task_....md`

## VERIFY / pytest

```
VERIFY:
- pytest -q --tb=line
```

pip install только если VERIFY содержит pytest или `AUTO_PIP_INSTALL=1`.
