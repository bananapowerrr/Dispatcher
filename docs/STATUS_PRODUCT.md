# AgentBus / NVCode — статус продукта (offline)

## Этап

**0.10-alpha+ / Feature completion (FC-38…48 + P0–P6 UI)**  
Live (Ollama/Aider) ещё не прогонялся — следующий крупный гейт после возвращения к ПК.

## Закрыто (контракты + UI)

| Блок | Статус |
|------|:---:|
| P0 Plan persistence + DecisionQueue MODIFY/REPLAN | ✅ |
| P1 Runtime hardening / silent-except audit (docs) | ✅ |
| P2 Plan UX (add/edit/reorder/cancel/notes/deps) | ✅ |
| P3 Editor foundation (find/replace, dirty) | ✅ |
| P4 Workspace (activity bar, terminal, search, layouts) | ✅ |
| P5 Agent UX (inline diff, Continue, Problems→Editor) | ✅ |
| P6 Project Health (audit/workflow/в план/в очередь) | ✅ |
| LivingPlan ↔ task_id ↔ DONE/ERROR | ✅ |

## Продуктовый цикл (уже в UI)

```
Project Center: Аудит → Что дальше? → В план → В очередь
Chat: /audit /health /plan /workflow /enqueue /compose
DONE → inline Diff Apply/Reject → Continue (enqueue next step)
Plan panel: В очередь / DONE по шагу
```

## Не делать до live

- parallel > 1, MCP, embeddings RAG
- новый UI framework
- объявлять 1.0 без 10 реальных задач

## После ПК

1. doctor + offline pytest  
2. LIVE_ACCEPTANCE (skill → ollama → aider → verify → retry)  
3. только точечные фиксы по логам
