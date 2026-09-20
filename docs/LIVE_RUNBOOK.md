# LIVE RUNBOOK — первый день на ПК

**Правило:** GitHub = source of truth. OpenCode правит локальный tree → pytest → commit.  
**Не трогать:** FSM, DONE gate, Plan model, AI-фичи, UI rewrite.

## 0. Один раз

```bash
cd AgentBus   # или клон с GitHub
pip install -r requirements.txt
pip install -r requirements-ui.txt   # если UI
ollama pull qwen2.5-coder:7b
# optional meta:
# ollama pull qwen2.5:1.5b-instruct

# sandbox project
mkdir -p ~/agentbus_sandbox && cd ~/agentbus_sandbox
git init
echo "def hello():\n    return 1\n" > app.py
git add . && git commit -m init
```

`.env` (минимум): `AGENTBUS_MAX_PARALLEL_PROJECTS=1`

## 1. Offline gate (должен быть GREEN)

```bash
cd AgentBus
bash scripts/ci_offline.sh
```

Если RED — **не** идти в live. Чинить offline.

## 2. Doctor

```bash
python dispatcher.py --doctor
# ожидание: VERDICT: READY (или DEGRADED с понятной причиной)
```

## 3. Mock path (ещё раз)

```bash
python scripts/live_smoke.py --mock
# смотри .agentbus/runs/*/summary.md
```

## 4. Первый live (минимум)

1. `python dispatcher.py` или UI  
2. Project = `~/agentbus_sandbox`  
3. Chat: `Добавь docstring к hello() в app.py`  
4. Дождись terminal status  
5. Проверь: `git diff`, History report, `.agentbus/runs/`  

**Критерий успеха первого live:**

```
задача → worker → реальное изменение файла → verify → DONE
```

Не «команда завершилась», а **файл изменился + verify PASS + status DONE**.

## 5. Негатив (обязательно в тот же день)

Chat: намеренно попроси сломать синтаксис / или подставь fail verify.  
Ожидание: **не DONE**.

## 6. Сбор evidence после каждого прогона

```bash
# последний run
ls -lt .agentbus/runs | head
cat .agentbus/runs/<id>/summary.md
```

Скопируй `summary.md` + `result.json` (и diff если есть) в issue/chat для аудита.

## 7. Crash / restart

1. Запусти длинную задачу  
2. Убей dispatcher  
3. Запусти снова  
4. Ожидание: reclaim / orphan plan → PENDING, нет ложного DONE  

## 8. Классификация сбоя

| Код | Слой | Примеры |
|-----|------|---------|
| ENV | окружение | нет ollama, нет git, path |
| PROVIDER | API/local server | 11434 down, no model |
| WORKER | aider/opencode/cli | exit≠0, empty output |
| EXECUTOR | subprocess | timeout, pipe, kill |
| VERIFY | verification | syntax/tests fail |
| RUNTIME | FSM/queue | stuck processing, false DONE |
| PLAN | living plan | orphan, wrong terminal |
| UI | display only | wrong status text |

Заполняй `docs/templates/LIVE_BUG.md`.

## 9. STOP conditions

- false DONE (verify fail но status DONE) → **P0 stop**  
- git reset --hard потерял чужие правки → **P0 stop**  
- бесконечный retry → **P0 stop**  

## 10. После 5–10 успешных задач

Только тогда: OpenCode + багфиксы по LIVE-BUG-*, не новые фичи.
