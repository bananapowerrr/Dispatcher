# NVCode Progressive UX — план (поверх FC-44…48)

## Уже сделано (не дублировать)

| Блок | Где |
|------|-----|
| Agent behavior autonomy/suggestions/arch/verify | `app/agent_behavior.py` |
| Named profiles beginner/developer/advanced/auto | `apply_profile()` / `list_profiles()` |
| Workspace modes CODE/AGENT/PROJECT | `app/workspace_mode.py` |
| Layout presets + ui.yaml | `app/layout_prefs.py` |
| Suggestions | `AgentService.suggestions()` |
| Post-DONE actions | `ChangesService.post_done_actions()` |
| Post-step report + checkbox next | `app/post_step_report.py` |
| Workflow Audit→Plan→Queue | `app/project_workflow.py` |
| Task composer | `app/task_composer.py` |
| Help popover `?` | `ui/help_popover.py` |
| Nav back/forward | `main_window` + `nav_history` |
| Runtime feedback | `TasksService.runtime_feedback()` |
| explain_context | `AgentService.explain_context()` |

## Продуктовые принципы (зафиксировано)

1. Intelligence предлагает → Runtime решает → Verify закрывает DONE.
2. Autonomy ≠ Suggestions (раздельные оси).
3. Task DONE ≠ Project READY.
4. Recommendations ≠ auto tasks (только после явного Continue/checkbox).
5. Profile = default; session/task override без молчаливой смены правил.
6. UI проще внутренней архитектуры (не вкладка на каждый модуль).

## Осталось (приоритет)

### P0 — UX glue (без нового backend)
1. Agent popover в toolbar: profile + 4 dropdown (модель уже есть).
2. После DONE в Chat: показать `build_post_step_report` + кнопки Continue/Review/Undo.
3. Continue с выбранными checkbox → `continue_selected()`.
4. Вставить `why_button` / HelpPopover в Health findings и report.

### P1 — Run loop (stub ok)
5. Run / Stop entry в UI (даже если runner = subprocess placeholder).
6. Проброс runtime error → Agent context (контракт, не полный runner).

### P2 — polish
7. First-run profile chooser (4 кнопки, не анкета).
8. «Привычка» — только явное предложение сменить профиль, не silent.
9. FC-46 layouts resize persistence уже частично есть.

## Не делать сейчас
- Новый FSM / вторая очередь / Jira
- MCP, RAG 2.0, parallel>1
- Автосоздание десятков tasks из audit
