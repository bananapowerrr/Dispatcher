# Recipes Analysis — AgentBus

## Существующие рецепты (7)

| # | Файл | Сценарий | Complexity |
|---|------|----------|------------|
| 1 | `01_refactor.json` | Рефакторинг файла | 3 |
| 2 | `02_test_coverage.json` | Покрытие тестами | 3 |
| 3 | `03_bugfix.json` | Исправление бага | 3 |
| 4 | `04_docstrings.json` | Добавление docstrings | 2 |
| 5 | `05_types.json` | Добавление type hints | 2 |
| 6 | `06_explain.json` | Объяснение кода | 1 |
| 7 | `07_cleanup.json` | Очистка кода | 2 |

## Формат рецепта

JSON-файл с полями:
- `id` — уникальный идентификатор
- `message` — промпт для модели
- `files` — список файлов (обычно пустой, задаётся при вызове)
- `metadata` — метаданные (recipe, complexity, task_type, prefer_local, source)

## Покрытые сценарии

- Базовый рефакторинг
- Тестирование
- Исправление багов
- Документирование (docstrings)
- Типизация
- Объяснение кода
- Очистка кода

## Gap Analysis — отсутствующие сценарии

### Критические пробелы

1. **Создание нового кода с нуля** — нет рецепта для генерации файла/функции
2. **Мультифайловые фичи** — нет рецепта для создания связанных файлов
3. **API endpoints** — нет рецепта для REST API
4. **Базы данных** — нет рецепта для миграций
5. **DevOps** — нет рецептов для Docker, CI/CD
6. **Безопасность** — нет рецепта для security-аудита
7. **Производительность** — нет рецепта для оптимизации
8. **Code review** — нет рецепта для ревью
9. **Модернизация legacy** — нет рецепта для обновления старого кода
10. **Генерация документации** — только docstrings, нет README/полной документации

### Добавлено в этой итерации (15 рецептов)

- `08_create_simple_file` — создание Python-файла
- `09_refactor_function` — рефакторинг функции
- `10_add_tests` — добавление тестов
- `11_fix_bug` — исправление ошибки
- `12_explain_code` — объяснение кода
- `13_multi_file_feature` — мультифайловая фича
- `14_api_endpoint` — REST API endpoint
- `15_database_migration` — миграция БД
- `16_docker_setup` — Docker + compose
- `17_ci_pipeline` — CI/CD
- `18_security_audit` — аудит безопасности
- `19_performance_optimization` — оптимизация
- `20_documentation_generation` — генерация документации
- `21_code_review` — ревью кода
- `22_legacy_modernization` — модернизация legacy

## Воркеры (config/workers.yaml)

| Воркер | Провайдер | Модель | Complexity | Billing |
|--------|-----------|--------|------------|---------|
| aider_local | ollama | qwen2.5-coder:7b | 2 | free |
| opencode | zen | — | 5 | free (plan only) |
| aider_siliconflow | siliconflow | dynamic | 5 | paid |
| aider_openrouter | openrouter | dynamic | 4 | paid |
| aider_together | together | dynamic | 5 | paid |
| aider_huggingface | huggingface | dynamic | 4 | paid |

## Провайдеры (config/providers.yaml)

| ID | Тип | Приоритет | Billing |
|----|-----|-----------|---------|
| ollama | ollama | 100 | local |
| lmstudio | openai_compatible | 95 | local |
| siliconflow | openai_compatible | 80 | free |
| openrouter | openai_compatible | 60 | free |
| together | openai_compatible | 40 | free |
| huggingface | openai_compatible | 30 | free |
