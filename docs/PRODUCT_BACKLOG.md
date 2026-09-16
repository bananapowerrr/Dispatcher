# AgentBus — Product completion backlog (без новых подсистем)

**Стратегия:** довести существующее от UI до результата.  
Старый audit-план (P0-01…P0-09) **не выбрасываем** — возвращаемся к нему после 10 живых задач, точечно.

**Не делаем сейчас:** MCP, RAG v2, parallel>1, multi-worktree, новый UI, autopilot v2, router rewrite.

---

## Главный сценарий (критерий готовности)

```
Открыть UI → задача → intake → worker/skill → файлы изменены
  → verify → результат в чате → DONE | ERROR (+ причина)
```

Если этот путь живой — продукт есть. Если нет — чиним только его.

---

## Backlog (~12 задач по ценности)

### PC-01 — Live checklist (offline готов)
Единая инструкция: doctor → start → 1 задача → diff → verify → DONE.  
**DoD:** `docs/LIVE_ACCEPTANCE.md` + шаги без философии.  
**Статус:** ✅ LIVE_ACCEPTANCE.md

### PC-02 — Skill rename/format от UI до файла
Уже: intake, `message=` для rename, SKILLS singleton.  
**DoD live:** «переименуй foo в bar» в чате → файл на диске.  
**Offline:** regression есть (`test_skill_dispatcher_contract`).

### PC-03 — Worker path (Aider/Ollama) end-to-end
Код: `rp_llm` → executor → verify → DONE + diff capture.  
**DoD live:** одна правка README/комментария через aider_local.  
**Offline:** не выдумывать; mock E2E уже есть.

### PC-04 — UI показывает Running → DONE/ERROR
Есть poll + phase_label.  
**Offline fix 2026-09-14:** nested `result` dict now flattened (`ui/result_text.py`); deferred state visible.  
**DoD live:** пользователь видит статус без чтения сырых логов.

### PC-05 — Verify fail → не DONE → retry
Код: verification_engine + bump attempts.  
**DoD live:** намеренно ломающий тест → ERROR/RETRY, не false-DONE.

### PC-06 — Timeout worker → наблюдаемый ERROR
Executor ExecutionResult.timed_out.  
**DoD live:** короткий timeout / зависшая модель → UI видит timeout.

### PC-07 — Diff в UI (если feature on)
`diff_engine` + diff_panel.  
**DoD live:** после DONE есть что Accept/Reject или хотя бы preview.

### PC-08 — Doctor = «можно стартовать»
Уже: schema, intake, workers.  
**DoD:** `python dispatcher.py --doctor` → VERDICT понятен новичку.

### PC-09 — Одна тестовая песочница проекта
Рецепт или `recipes/` + инструкция «создай sandbox».  
**DoD:** не гонять автопилот на боевом репо с dirty tree.

### PC-10 — Ошибка в чате человеческим языком
**Offline fix 2026-09-14:** ERROR shows worker/skill/stage + hints (timeout/verify/busy); phase_label «✗ ошибка».  
**DoD live:** подтвердить на реальном verify-fail.

### PC-11 — Reclaim не дублирует при parallel=1
Код есть.  
**DoD live:** одна stuck задача → requeue без второго worker на тот же project.

### PC-12 — Заморозка architecture
Любой PR/патч: «это чинит main path?» Если нет — backlog audit later.

---

## Порядок работы в отъезде (сокращённый)

| День | Фокус |
|------|--------|
| 1 | PC-01 LIVE_ACCEPTANCE + product_smoke imports |
| 2–3 | PC-02/04/08 — закрыть offline gaps на UI↔queue↔skill |
| 4 | PC-10 тексты ошибок (если gap в коде) |
| 5 | Остановка. Не начинать P0-02 exhaustive без нужды |
| После ПК | PC-03,05,06,07,11 строго по live |

---

## Связь со старым audit-планом

| Когда | Что |
|-------|-----|
| После 10 live задач | P0-02 DONE paths, P0-04 executor edges — только по симптомам |
| Если false-DONE | P0-02 + P0-07 |
| Если dual execution | P0-05 reclaim |
| Если git wipe | P0-06 |

**Счётчик успеха:** не «% аудитов», а **N подряд успешных пользовательских задач**.

### PC-13 — Desktop channel tree always exists
**Offline fix 2026-09-14:** `FileBus.ensure()` всегда создаёт `channels/desktop/*` (даже если нет в AGENTBUS_CHANNELS).  
Chat `send_task` использует id из `put()` и phase «○ в очереди».

### PC-14 — Doctor видит desktop channel
**Offline fix 2026-09-14:** `doctor` check `desktop_channel` + `FileBus.ensure()` с CHANNELS; product_path_check покрывает ensure+write.

### PC-15 — UI startup + история с итогом
**Offline fix 2026-09-14:** `main_window._ensure_desktop_bus` при старте; `history_panel` показывает extract_result_text для done/errors/deferred.

### PC-16 — History details + logs chat counter
**Offline fix 2026-09-14:** детали задачи — summary через result_text; logs queue chat:N из desktop_queue spill.

### PC-17 — History Resend → desktop_queue
**Offline fix 2026-09-14:** `_resend_task` больше не пишет только в `channels/*/incoming`; primary = `local_queue` (desktop), phone mirror optional.

### PC-18 — Recipes → desktop_queue only
**Offline fix 2026-09-14:** `emit_recipe` больше не пишет в `channels/*/incoming` по умолчанию; fail если queue put упал; phone mirror только по флагу.

### PC-19 — Web dashboard → desktop_queue only
**Offline fix 2026-09-14:** POST task больше не падает в `channels/gpt/incoming` при ошибке queue; 400 на reject, 500 на queue fail.

### PC-20 — agentbus init создаёт desktop tree
**Offline fix 2026-09-14:** `ensure_agentbus_dirs` → FileBus.ensure() + `.agentbus/desktop_queue`, не только gpt/incoming.

### PC-21 — diagnose desktop channel
**Offline fix 2026-09-14:** `--diagnose` вызывает FileBus.ensure() и печатает desktop channel OK/MISSING.

### PC-22 — Log DONE/ERROR → human summary
**Offline fix 2026-09-14:** `logs_panel` при task_id подтягивает summary из channels/*/done|errors JSON (extract_result_text) для toast/chat.

### PC-23 — Recipes → pending_ids
**Offline fix 2026-09-14:** после emit_recipe UI добавляет task_id в chat._pending_ids, иначе poll не показывает DONE.

### PC-24 — Chat recipe dropdown + Ctrl+K recipe → pending_ids
**Offline fix 2026-09-14:** `_run_recipe` и command palette `recipe_refactor` добавляют id в pending для poll.

### PC-25 — Deferred desktop reclaim
**Bug:** deferred desktop → `channels/desktop/deferred` → recover → incoming, но claim брал только local_queue (phone off) → вечный DEFERRED.  
**Fix:** `_active_channels` + desktop; claim всегда сканирует `desktop/incoming` (`only_channels`).
**Regression:** `tests/test_deferred_desktop_claim.py` (3 passed).

### PC-26 — DEDUPED → terminal done
**Bug:** дубликат возвращал DEDUPED без JSON в done/ → chat pending_ids не очищался.  
**Fix:** `_finalize_deduped` пишет `channels/<ch>/done` с method=dedupe.  
**Test:** `tests/test_dedupe_finalize.py`

### PC-27 — Early ERROR/DONE terminal JSON
**Bug:** pre_hook abort → ERROR без errors/; decompose parent → DONE без done/ → pending висит.  
**Fix:** `_finalize_early_terminal` + вызовы из pre_hook / decompose.  
**Test:** `tests/test_early_terminal.py`

### PC-28 — ProjectContext ERROR + pending stale
**Bug1:** падение `ProjectContext` → `_save(errors)` без `bus.move` / emit / trace.  
**Bug2:** `pending_ids` без TTL при исчезнувшей задаче.  
**Fix:** полный terminal path; `_track_pending` + предупреждение 30 мин / сброс 2 ч.

### PC-29 — First-run dirs + dispatcher hint
**Fix1:** `setup_wizard._finish` → `ensure_agentbus_dirs` (desktop tree).  
**Fix2:** pending в spill >60с → «запустите диспетчер»; иначе 30мин reclaim hint.

### PC-30 — Сразу подсказка «диспетчер не запущен»
При enqueue из чата / resend / recipe, если `dispatcher_ctl.is_running()==False` → system message про ▶.

### PC-31 — Статус диспетчера без ложного «работает»
**Bug:** наличие JSON в `*/processing` считалось running=True при мёртвом процессе.  
**Fix:** running только `disp_is_running` / lock-файл; orphan processing показывается отдельно.

### PC-32 — is_running видит CLI-диспетчер
**Bug:** UI `is_running` смотрел только `dispatcher_ui.pid`; CLI `python dispatcher.py` был «не запущен».  
**Fix:** парсинг `DispatcherLock` / lock-файлов с проверкой PID; stop: SIGTERM→SIGKILL.

### PC-33 — /status + Ctrl+Enter
**Fix:** slash `/status` показывает dispatcher ON/OFF и desktop queue.  
**Fix:** Ctrl+KP_Enter и bind на input (Windows/разные раскладки).

### PC-34 — Entry points cleanup
**Bug:** `dispatcher.py` / `dispatcher_ui.py` / `admin_ui.py` — мусорные docstring `'''"""main()."""'''`; plugins path не добавлялся.  
**Fix:** чистые entry scripts, корректный `sys.path` (root, src, plugins).

## Feature completion (post offline path)

### FC-01 — TaskResult product contract
- `core/task_result.py`: ChangeSet, SkillResult, TaskResult, build_task_result, format_human
- skills.execute → skill_result / files_changed
- runtime `_save` embeds `result.task_result` on terminal states
- history «детали» shows human timeline
- `core/task_service.py` submit() → intake + desktop_queue
- tests: `test_task_result_contract.py` (4 passed)

### FC-02 — Verification as product report
- `VerificationReport`: duration_sec, summary_line(), format_human(), richer to_dict
- `CheckResult.duration_sec`
- engine `run()` fills total duration
- chat/history prefer TaskResult + verify summary on DONE/ERROR
- tests: test_verification_report_ui (3) + task_result still green

### FC-03 — History product cards
- `history_card_lines()` in task_result (worker, skill, duration, verify, files)
- history_panel row shows meta / Verify PASS|FAIL / files
- details still full TaskResult.format_human + JSON
- tests: test_history_card (2) — 9 contract tests green total

### FC-04 — ChangeSet from git / file_changes
- `GitOps.change_set_since()` → files + numstat insertions/deletions
- `build_task_result` reads change_set, file_changes, files_changed
- rp_llm after diff capture writes metadata.change_set + result.files_changed
- history cards show `N file(s)` and +/- when available
- tests: test_changeset_fc04

### FC-05 — Skills → unified SkillResult
- SkillResult.from_execute harvests files/errors from format/hygiene/refactor shapes
- _pack_skill_out marks nested error as failure; catalog()
- _try_skill / _finalize_skill_result propagate skill_result + files_changed to DONE JSON
- tests: test_skill_result_fc05 (4)

### FC-06 — UI current task
- `ui/current_task.py`: find_active_task, format_current_task
- main_window sidebar strip + poll with dispatcher status
- tests: test_current_task_fc06

