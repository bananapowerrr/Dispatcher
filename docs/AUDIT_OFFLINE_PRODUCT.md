# Аудит offline product path (сент 2026)

## Цель периода

Не наращивать AI-фичи. Закрыть **пользовательский цикл** до первого live:

```
UI/CLI → desktop_queue → claim → process → verify → DONE/ERROR
         + статус диспетчера, pending, terminal JSON
```

---

## Сделано (PC-25 … PC-34)

| ID | Суть | Статус |
|----|------|:---:|
| PC-25 | deferred/stuck desktop → claim `desktop/incoming` | ✅ |
| PC-26 | DEDUPED пишет `done/` (pending UI) | ✅ |
| PC-27 | pre_hook ERROR + decompose parent DONE → terminal JSON | ✅ |
| PC-28 | ProjectContext ERROR полный path; pending TTL 30м/2ч | ✅ |
| PC-29 | setup_wizard ensure dirs; spill>60с → «запустите диспетчер» | ✅ |
| PC-30 | сразу hint если dispatcher OFF при enqueue | ✅ |
| PC-31 | статус не врёт «работает» из orphan processing | ✅ |
| PC-32 | `is_running` / stop видят CLI DispatcherLock PID | ✅ |
| PC-33 | `/status` queue+dispatcher; Ctrl+KP_Enter | ✅ |
| PC-34 | чистые `dispatcher.py` / `dispatcher_ui.py` / `admin_ui.py` | ✅ |

**Ранее (PC-04…24):** единый intake desktop_queue, resend/recipes/pending_ids, result_text, doctor desktop, history details.

**Regression:** `scripts/product_path_check.py` → **7/7 GREEN** (offline, без Ollama).

---

## Архитектура product path (актуально)

```
Chat / Recipes / Resend / Web
        │
        ▼
  desktop_queue (.agentbus/desktop_queue + memory)
        │
        ▼
  Runtime.claim: local_queue → _claim_desktop_incoming → (phone?)
        │
        ▼
  process → skills/cache/LLM → verify gate
        │
        ├── done/   → UI poll → notify_done
        ├── errors/ → notify_error
        └── deferred/ → recover → desktop/incoming → claim
```

---

## Что осталось (только с ПК / live)

### P0 — Live acceptance (обязательно)

1. `python dispatcher.py --doctor` (или diagnose) — VERDICT OK  
2. Ollama: `qwen2.5-coder:7b` (+ meta 1.5b опционально)  
3. Два процесса: `dispatcher.py` + `dispatcher_ui.py`  
4. Матрица 5 задач из `docs/LIVE_ACCEPTANCE.md`  
5. Подтвердить: **нет false-DONE**, pending сбрасывается, ▶ status верный  

### P1 — по результатам live

- Aider/worker timeout на реальном железе  
- Diff Apply/Reject на реальном git  
- Reclaim stuck после kill -9 диспетчера  
- Quota/provider 429 fallback  

### P2 — не сейчас

- Parallel > 1 / worktree  
- MCP, embeddings RAG  
- Новые провайдеры / большой UI rewrite  
- Полноценный autopilot night load  

---

## Риски на live (честно)

| Риск | Митигация в коде | Проверить руками |
|------|------------------|------------------|
| False DONE | verify gate | задача 4 в матрице |
| Зависший pending | PC-26…28 terminal + TTL | DEDUPED, hook abort |
| «Диспетчер OFF» при CLI | PC-32 is_running | start CLI, смотреть LED |
| Dirty git park | dirty policy | dirty sandbox |
| OOM 7B+meta | keep_alive / одна модель | doctor models |

---

## Рекомендация

**Offline product path заморозить.** Дальше — только live checklist.  
Новые фичи — после 5–10 успешных реальных задач подряд.
