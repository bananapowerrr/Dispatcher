# Первый запуск (машина)

## 1. Offline (без моделей)

```bash
cd AgentBus
python scripts/smoke_offline.py
python scripts/live_smoke.py --mock
bash scripts/ci_smoke.sh          # полный offline CI
```

Ожидание: `READY` / `OK (0.10-alpha offline CI)`.

## 2. Doctor

```bash
python dispatcher.py --diagnose
# или
python -c "from core.doctor import print_doctor; print_doctor()"
```

Critical must PASS. `local_runtime` / `ui_deps` могут быть NO до установки.

## 3. Локальный стек

```bash
ollama pull qwen2.5-coder:7b
ollama pull qwen2.5:1.5b-instruct   # meta
pip install -r requirements.txt
pip install -r requirements-ui.txt  # UI
```

## 4. Старт

```bash
python dispatcher.py              # демон
python dispatcher_ui.py           # чат ПК = основной канал
```

Preset для РФ: `beginner_ru` (local, parallel=1).

## 5. Первые задачи

1. Простая правка файла через UI  
2. Намеренный verify fail  
3. Retry  
4. Skill (format / normalize newlines) без LLM  

## Правило

Worker может «успеть» — **DONE** только после `gate_done` + verification.
