# AgentBus — чеклист первого запуска (LIVE)

Offline-архитектура закрыта. Этот документ — **acceptance на ПК**, не разработка.

## 0. Подготовка

```bash
cd AgentBus
pip install -r requirements.txt
pip install -r requirements-ui.txt
export PYTHONPATH=src:.
```

Опционально:

```bash
ollama pull qwen2.5-coder:7b
ollama pull qwen2.5:1.5b-instruct
```

Без моделей — режим **core-only** (skills / git / verify).

## 1. Диагностика

```bash
python dispatcher.py --doctor
```

В UI: diagnose → checklist + Configuration Advisor.

## 2. Тесты offline

```bash
python -m pytest -q tests/ --tb=line
```

## 3. UI

```bash
python dispatcher_ui.py
```

Setup Wizard → проект → skill-задача в чате.

## 4. LIVE минимум

1. Skill-only → DONE skill  
2. Правка файла → diff → verify → DONE  
3. Verify FAIL → не false-DONE  
4. Retry / deferred видны  
5. Architecture A/B при стопоре  
6. 5 задач подряд  

## 5. Красные флаги

DONE без verify · вечный processing · UI hang · concurrency>1 без worktree  

## 6. Откат

Feature flags выкл autopilot/night · core-only · логи `.agentbus/`
