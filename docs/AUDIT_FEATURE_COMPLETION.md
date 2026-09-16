# AgentBus — аудит Feature Completion (offline)

**Дата:** 2026-09-15  
**Режим:** product maturity, без live Ollama/Aider  
**Цель аудита:** передать GPT полный контекст без доступа к файлам.

---

## 1. Стратегия (зафиксирована)

Не freeze до live. Не новые подсистемы (MCP, RAG 2.0, parallel, multi-agent).

> Доводить существующие возможности до продукта.

Скелет продукта:

```
Task
  → Worker | Skill
  → ChangeSet
  → VerificationResult
  → TaskResult
  → UI (chat / history / current task)
```

---

## 2. Offline product path (ранее, PC-25…34) — GREEN

Единый intake `desktop_queue`, terminal JSON (DEDUPED/early ERROR/DONE), deferred reclaim desktop, pending TTL, dispatcher `is_running` (CLI+UI), entry points cleanup.

`scripts/product_path_check.py` → **7/7 GREEN**.

---

## 3. Feature Completion спринты (FC-01…06)

| ID | Спринт | Что сделано | Тесты |
|----|--------|-------------|------:|
| **FC-01** | TaskResult contract | `core/task_result.py`: ChangeSet, SkillResult, TaskResult, `build_task_result`, `format_human`; `task_service.submit`; `_save` embeds `task_result` | 4 |
| **FC-02** | Verification product | `VerificationReport.summary_line/format_human/duration`; chat DONE/ERROR через TaskResult+verify | 3 |
| **FC-03** | History cards | `history_card_lines`; history row: worker/skill/duration, Verify PASS/FAIL, files | 2 |
| **FC-04** | ChangeSet ↔ git | `GitOps.change_set_since` (numstat); rp_llm пишет `metadata.change_set`; build_task_result читает file_changes | 3 |
| **FC-05** | Skills unified | SkillResult harvest files/errors; pack nested errors; `_try_skill`/`_finalize_skill_result` → skill_result+files_changed в DONE | 4 |
| **FC-06** | UI current task | `ui/current_task.py`; sidebar «Текущая задача» в main_window poll | 2 |

**Суммарно новых offline-тестов по FC:** **18 passed** (pytest batch FC-01…06).

---

## 4. Ключевые файлы (куда смотреть)

```
src/core/task_result.py       # TaskResult / SkillResult / ChangeSet / history_card_lines
src/core/task_service.py      # submit() → intake + desktop_queue
src/core/verification_engine.py  # summary_line, duration_sec
src/core/runtime_ops.py       # _save embeds task_result
src/core/rp_llm.py            # change_set after diff capture
src/core/rp_cache_skills.py   # skill_result на DONE
src/safety/gitops.py          # change_set_since()
src/skills/skills.py          # _pack_skill_out, catalog
ui/history_panel.py           # product cards
ui/chat_panel.py              # extract via TaskResult
ui/current_task.py            # active task strip helpers
ui/main_window.py             # current_task_lbl + poll
ui/dispatcher_ctl.py          # CLI-aware is_running (PC-32)
tests/test_*_fc*.py / test_task_result_contract.py / test_history_card.py / test_verification_report_ui.py
docs/PRODUCT_BACKLOG.md
docs/LIVE_ACCEPTANCE.md
docs/AUDIT_OFFLINE_PRODUCT.md
```

---

## 5. Контракты (кратко)

### TaskResult
- `task_id, status, ok, worker, skill, duration_sec, attempts`
- `summary, error, changes: ChangeSet, verification: dict, timeline`
- `format_human()` для чата/history details

### ChangeSet
- `files, insertions, deletions, patch_preview`
- источники: `result.change_set`, `metadata.file_changes`, `files_changed`, git numstat

### SkillResult
- `success, name, message, error, changed, files, data`
- `from_execute` понимает format/hygiene/refactor/nested error shapes

### VerificationReport
- `passed, checks[], reason, risk, duration_sec`
- `summary_line()`, `format_human()`, `to_dict()["summary"]`

### TaskService
- `submit(message, project=, files=, source=)` → validate/intake → `local_queue.put`

---

## 6. UI product path (как видит пользователь)

```
Chat send → desktop_queue
  → (если dispatcher OFF: сразу hint ▶)
  → processing → phase_label + sidebar «Текущая задача»
  → done/errors → TaskResult human text в чате
  → history: meta · Verify · files · [детали] [↻]
```

---

## 7. Что ещё можно довести offline (опционально)

По GPT-плану 6 спринтов **закрыты**. Точечно, без новых подсистем:

1. **Workers panel** — показывать WorkerResult.ok/latency из последнего DONE (read-only из history JSON).
2. **Skills panel** — вызов `catalog()` + last skill_result message.
3. **Diff panel** — если pending_diffs есть, связать с ChangeSet.files из TaskResult.
4. **Единый TaskService** в chat.send_task / recipes (сейчас queue напрямую; service уже есть).

Это polish, не блокеры.

---

## 8. Что нельзя закрыть offline (только live)

| Пункт | Почему |
|-------|--------|
| Ollama/Aider real execute | нет модели/CLI на этой среде |
| False-DONE на реальных тестах | нужен pytest в sandbox-проекте |
| Timeout/kill subprocess | нужен hung worker |
| Diff Apply на реальном git | нужен worktree |
| 5–10 задач подряд acceptance | `LIVE_ACCEPTANCE.md` |

Критерий 0.10-beta: матрица из LIVE_ACCEPTANCE + нет false-DONE.

---

## 9. Риски при первом live

1. **Старые JSON в channels** без `task_result` — UI fallback на extract_result_text (OK).
2. **Skill DONE без files** — SkillResult.changed false; history без files line (OK).
3. **change_set_since** на non-git проекте — пустой ChangeSet (OK).
4. **Дубли files** на Drive при upload — пользователь может иметь 2 копии; код в src/ каноничен.
5. **customtkinter** не в offline CI UI import — тесты current_task/history_card без ctk.

---

## 10. Рекомендация GPT / владельнику

1. Считать **offline product skeleton закрытым** (FC-01…06 + PC path).
2. Не начинать MCP / parallel / RAG 2.0.
3. На ПК: `LIVE_ACCEPTANCE.md` → doctor → dispatcher + UI → 5 задач.
4. Баги после live — точечные fixes в том же контракте TaskResult, не новый framework.
5. Опциональный offline polish: п.7 (workers/skills/diff panels read-only).

---

## 11. Команды проверки (offline)

```bash
cd AgentBus
PYTHONPATH=src:. python scripts/product_path_check.py
PYTHONPATH=src:. python -m pytest tests/test_task_result_contract.py \
  tests/test_verification_report_ui.py tests/test_history_card.py \
  tests/test_changeset_fc04.py tests/test_skill_result_fc05.py \
  tests/test_current_task_fc06.py -q
# ожидается: product_path GREEN, 18 passed
```

---

## 12. Итог одной фразой

AgentBus offline теперь не только «надёжный runtime», а **сквозной product path** с единым TaskResult от skill/worker через verify и git changes до chat/history/current-task UI; live остаётся проверкой адаптеров (Ollama/Aider), а не пересборкой архитектуры.
