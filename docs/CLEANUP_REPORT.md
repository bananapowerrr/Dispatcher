# Cleanup Report

## Дата: 2026-10-08
## Всего файлов в репозитории: 777
## Мусор: 25 файлов

## К удалению (DELETE)
| Файл | Причина | Размер |
|------|---------|--------|
| `test_cache_1.py` | Тест в корне репозитория, не в `tests/`. Содержит только `def hello(): return 'world'` | 34 B |
| `Modelfile-t-lite` | Ollama Modelfile, не относится к проекту | 138 B |
| `.agentbus/desktop.ini` | Windows OS мусор | 352 B |
| `.agentbus/sessions/desktop.ini` | Windows OS мусор | 352 B |
| `.agentbus/desktop_queue/desktop.ini` | Windows OS мусор | 352 B |
| `.agentbus/uploads/desktop.ini` | Windows OS мусор | 352 B |
| `.agentbus/uploads/att1/desktop.ini` | Windows OS мусор | 352 B |
| `src/core/__pycache__/desktop.ini` | Windows OS мусор в исходниках | 352 B |
| `src/intelligence/__pycache__/desktop.ini` | Windows OS мусор в исходниках | 352 B |
| `src/safety/__pycache__/desktop.ini` | Windows OS мусор в исходниках | 352 B |
| `src/skills/__pycache__/desktop.ini` | Windows OS мусор в исходниках | 352 B |
| `src/skills/builtin/__pycache__/desktop.ini` | Windows OS мусор в исходниках | 352 B |
| `src/utils/__pycache__/desktop.ini` | Windows OS мусор в исходниках | 352 B |
| `providers/__pycache__/desktop.ini` | Windows OS мусор в исходниках | 352 B |
| `plugins/__pycache__/desktop.ini` | Windows OS мусор в исходниках | 352 B |
| `eventbus/__pycache__/desktop.ini` | Windows OS мусор в исходниках | 352 B |
| `scripts/__pycache__/` | Python cache (9 директорий) | -- |
| `src/core/__pycache__/` | Python cache | -- |
| `src/intelligence/__pycache__/` | Python cache | -- |
| `src/safety/__pycache__/` | Python cache | -- |
| `src/skills/__pycache__/` | Python cache | -- |
| `src/utils/__pycache__/` | Python cache | -- |
| `providers/__pycache__/` | Python cache | -- |
| `plugins/__pycache__/` | Python cache | -- |
| `eventbus/__pycache__/` | Python cache | -- |

## К переносу (MOVE)
| Файл | Куда | Причина |
|------|------|--------|
| `.opencode/` | `~/.config/opencode/` или `.gitignore` | 3,938 файлов node_modules, 12.7 MB |
| `.kilo/` | `.gitignore` или удалить | Kilo agent worktrees |
| `events/2026-10-08.jsonl` | `logs/` или `.gitignore` | Runtime event log |
| `docs/rp_llm_meta_decompose.diff.txt` | `patches/` или git history | Diff файл не место в docs/ |

## К обсуждению (REVIEW)
| Файл | Вопрос |
|------|--------|
| `docs/SYNC_SCRIPT_AUDIT.md` | Содержит аудит внешнего скрипта `D:\Workspace\mirror-to-drive.ps1`, которого нет в репозитории. Галлюцинации? |
| `docs/AUDIT_2026-09-22.md` | Старый аудит (1+ месяц). Актуален? |
| `docs/PCGAP_PRODUCT_INTEGRATION_AUDIT.md` | Аудит с git-хэшами. Актуален после синхронизации? |
| `docs/DAY21_PRODUCT_READINESS_AUDIT.md` | Большой аудит с gap matrix. Актуален? |
| `docs/release.json` | Автогенериемый метаданные релиза. Нужен в репозитории? |
| `docs/release.example.json` | Пример метаданных релиза. Оставить? |
| `tests/ui.yaml` | Конфиг в папке tests/. На месте ли? |

## Что оставить (KEEP)
- `src/` — весь исходный код проекта
- `tests/` — все тесты (220+ файлов), skip/xfail с объяснениями
- `docs/` — документация, архивы, шаблоны
- `config/` — конфигурационные файлы
- `scripts/` — скрипты проекта
- `ui/` — интерфейс
- `providers/`, `plugins/`, `eventbus/`, `recipes/`, `examples/` — модули проекта
- `AGENTS.md`, `README.md`, `pyproject.toml`, `requirements*.txt`, `pytest.ini` — базовые файлы
- `.github/` — CI/CD конфигурация
- `.gitignore` — добавить `.opencode/`

## Приоритетные действия
1. Добавить `.opencode/` в `.gitignore` — 12.7 MB node_modules
2. Удалить `test_cache_1.py` — мусор в корне
3. Удалить `Modelfile-t-lite` — не относится к проекту
4. Проверить `SYNC_SCRIPT_AUDIT.md` — возможные галлюцинации
5. Перенести `rp_llm_meta_decompose.diff.txt` из `docs/`
6. Очистить `desktop.ini` из исходников (13 файлов)
7. Очистить `__pycache__` из исходников (9 директорий)
