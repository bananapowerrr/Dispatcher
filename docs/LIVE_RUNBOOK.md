# LIVE_RUNBOOK.md — как гонять сценарии и поддерживать AgentBus в живом виде

> Дата: 2026-10-08. Смежники: `docs/LIVE_ACCEPTANCE_SUITE.md` (сценарии LIVE-001…LIVE-022), `docs/templates/LIVE_BUG.md` (формат бага), `docs/CONTRACTS_AUDIT.md`, `docs/TECHNICAL_DEBT_REGISTRY.md`.
> Виртуальная среда: `D:\Workspace\.venv\Scripts\python.exe` (вне репо, т.к. облачная копия медленная). PYTHONPATH задаёт `run-tests.ps1` = `src;.`.

## 1. Оффлайн-гейт (обязателен перед сдачей)

```bash
bash scripts/ci_offline.sh
```

Что внутри (см. сам скрипт): матрица оффлайн-приёмки (`offline_acceptance_matrix`), live-smoke на моках (`live_smoke --mock`), doctor-диагностика (`--diagnose` от runtime), выборочный pytest по критичным контрактам и preflight `live001`. Гейт должен быть зелёным.

Windows-эквивалент для тестов:
```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File run-tests.ps1
# один файл / по ключу:
powershell -NoProfile -ExecutionPolicy Bypass -File run-tests.ps1 tests/test_reclaim.py
powershell -NoProfile -ExecutionPolicy Bypass -File run-tests.ps1 -k "billing or paid"
```

Проверка числа тестов (на 2026-10-08 собирается **1823**, не 1723 — см. TD-022):
```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File run-tests.ps1 --collect-only | Select-String "collected"
```

## 2. Как запустить рантайм / диспетчер / диагностику

```powershell
# file-bus воркер (каналы из AGENTBUS_CHANNELS, по умолчанию gpt,grok,gemini,autopilot)
powershell -NoProfile -ExecutionPolicy Bypass -File run-tests.ps1  # не для рантайма; используйте python напрямую:
& "D:\Workspace\.venv\Scripts\python.exe" -m core.runtime

# доктор-диагностика
& "D:\Workspace\.venv\Scripts\python.exe" -m core.runtime --diagnose

# диспетчер: версия / init-визард / рецепты
& "D:\Workspace\.venv\Scripts\python.exe" -m core.dispatcher_main --version
& "D:\Workspace\.venv\Scripts\python.exe" -m core.dispatcher_main init
& "D:\Workspace\.venv\Scripts\python.exe" -m core.dispatcher_main --recipe list
& "D:\Workspace\.venv\Scripts\python.exe" -m core.dispatcher_main --recipe <NAME> --target <PATH>

# ночной планировщик соло
& "D:\Workspace\.venv\Scripts\python.exe" -m intelligence.night_scheduler
```

## 3. Гонка сценариев LIVE (таблица)

Каждый сценарий прогоняется одним из способов: **A** — через file-bus (drop json в `channels/<CH>/incoming/`), **B** — через desktop-чат (`LocalQueue`/UI), **C** — автоматизированный pytest (список тестов, помечающих сценарий). После сдачи — фиксировать `LIVE-XXX | run_id=... | PASS/FAIL | notes=` в `docs/LIVE_ACCEPTANCE_SUITE.md:99`.

| LIVE | Сценарий | Способ | Ключевая проверка |
|------|----------|--------|-------------------|
| LIVE-001 | Create file | A/C | файл создан, задача в `done/` |
| LIVE-002 | Edit existing | A/C | diff только по задаче |
| LIVE-003 | Multi-file | A/C | несколько файлов в одной задаче |
| LIVE-004 | Bugfix | A/C | план + фикс + verify |
| LIVE-005 | Add test | A | тест добавлен и проходит |
| LIVE-006 | Verify PASS | A | `verification_allows_done` → done |
| LIVE-007 | Verify FAIL | A | повтор/ERROR, НЕ DONE |
| LIVE-008 | Retry → DONE | A | retry-политика доводит до done |
| LIVE-009 | Retry exhausted → ERROR | A | задача уходит в `errors/` |
| LIVE-010 | Worker timeout | A/C (cron-тесты fc14) | error-строка с evidence |
| LIVE-011 | Worker crash | A | reclaim возвращает в обработку |
| LIVE-012 | Empty output | A | трактуется как ошибка |
| LIVE-013 | Invalid output | A | reject без DONE |
| LIVE-014 | No-op worker | A | нет «пустого» DONE |
| LIVE-015 | Dangerous command / path | B | `IntakeError` fail-closed (проверка путей) |
| LIVE-016 | Plan → Task → DONE | A | терминальная власть плана |
| LIVE-017 | Multi-step plan | A | шаги идут по порядку |
| LIVE-018 | Replan after failure | A | ошибка → replan → DONE |
| LIVE-019 | Restart / reclaim | A | перезапуск рантайма не дублирует задачи |
| LIVE-020 | Duplicate task | B | dedupe → ссылка на оригинал |
| LIVE-021 | Report UI (bonus) | B | отчёт в UI |
| LIVE-022 | /report <task_id> (bonus) | B | отчёт по id |

Пример drop-файла для способа A:
```json
{
  "id": "live-016",
  "channel": "gpt",
  "project": "demo",
  "message": "plan: создать файл hello.py с функцией add(a,b)",
  "files": [],
  "metadata": { "intake_source": "live" }
}
```
Положить в `channels/gpt/incoming/live-016.json` при работающем `python -m core.runtime`.

## 4. Night Mode

Включается env-флагом в том же воркере; тайминги/лимиты — через env (`src/intelligence/night_scheduler.py:38-54`).

```powershell
$env:AGENTBUS_NIGHT_MODE = "1"
$env:AGENTBUS_NIGHT_START = "22:00"
$env:AGENTBUS_NIGHT_END   = "06:00"
$env:AGENTBUS_NIGHT_MAX_TASKS = "20"
$env:AGENTBUS_NIGHT_MIN_COMPLEXITY = "3"
& "D:\Workspace\.venv\Scripts\python.exe" -m core.runtime
```

Проверка состояния через `night_mode_status()` (`night_mode_controller.py`); утром `report.py` кладёт отчёт в `done/`. Порядок проверки контрактов ночного цикла: `test_dev007_night_loop.py`, `test_night_rt_001.py`, `test_night_mode_r6.py`.

## 5. Troubleshooting

| Симптом | Диагноз | Действие |
|---------|---------|----------|
| Задача «висит» в `processing/` | Потеряна аренда / краш воркера | `reclaim.py` reclaim_stuck по lease; проверить `AGENTBUS`-logs |
| DONE-путь падает с `AttributeError: ...gitops...` при `AGENTBUS_GIT=1` | Было **TD-001**: вызов несуществующего `gitops.commit_plan` | Исправлено 2026-10-08 (`gitops.commit` + `build_commit_message`); при симптоме — убедиться, что код обновлён до фикса |
| Всё уходит в `deferred/` с платным провайдером | paid-gate консервативен (C-06) | Проверить провайдер в `paid_gate.py`, либо переложить задачу на локального воркера |
| `IntakeError` на входе | Небезопасный путь/payload | Исправить JSON (fail-closed — это ожидаемо) |
| Desktop-задачи не видны во второй процесс | spill-очередь `.agentbus/desktop_queue/` | Проверить файлы спилла (`local_queue.py`), очистить частично записанные |
| Один и тот же код-пример выполняет две копии (`rp_skills_stage` vs `rp_cache_skills._try_skill`) | TD-011: дубль логики | Прод использует `rp_cache_skills`; тесты до фикса смотрят на `rp_skills_stage` |
| Число тестов не совпадает с заявленным | TD-022 | Пересчитать `--collect-only` |
| Мутный/длинный лог ошибки | Для репорта | Снять `.agentbus/runs/<id>/` + заполнить `docs/templates/LIVE_BUG.md` |

## 6. Правила приёма и сдачи (лайф-цикл)

1. Прочитал `LIVE_RUNBOOK` → выбрал сценарий из `LIVE_ACCEPTANCE_SUITE`.
2. Запустил рантайм/UI → прогнал сценарий → зафиксировал результат в таблице приёмки (`PASS/FAIL` + `run_id`).
3. При FAIL: заполнить `docs/templates/LIVE_BUG.md`, приложить `.agentbus/runs/<id>/`, записать находку в `TECHNICAL_DEBT_REGISTRY.md` (если это долг).
4. Чинить **одну** категорию бага → перегнать тот же LIVE → пройти `bash scripts/ci_offline.sh` → коммит.
5. **Не** трогать FSM/DONE gate/терминальную власть плана/intake fail-closed без явного запроса (AGENTS.md, hard rules).