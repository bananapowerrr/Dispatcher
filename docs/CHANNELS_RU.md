# Каналы: desktop vs телефон

| Канал | Роль |
|--------|------|
| **Чат на ПК** | Основной. Очередь `.agentbus/desktop_queue/` |
| **channels/desktop/** | Результаты (done/errors) для UI |
| **channels/gpt/…** | Опционально: задачи с телефона через sync-папку |

По умолчанию `phone_filebus: false` в `config/feature_flags.yaml`.
