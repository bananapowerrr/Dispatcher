# Установка на Windows

## Быстрый старт (Python)

1. Установите Python 3.11+ с python.org (галочка PATH).
2. Скопируйте папку AgentBus.
3. В cmd:

```bat
cd AgentBus
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python dispatcher.py --init
python dispatcher.py --doctor
```

Ищи строку: `VERDICT: МОЖНО СТАРТОВАТЬ`.

4. Запуск:

```bat
python dispatcher.py
python dispatcher_ui.py
```

или двойной клик: `scripts\start_all.bat`, `scripts\start_ui.bat`.

## Ollama (локально, 0 ₽)

```bat
ollama pull qwen2.5-coder:7b
ollama pull qwen2.5:1.5b-instruct
```

## Сборка .exe (опционально)

```bat
pip install pyinstaller
python scripts\build_exe.py
```

Появятся `dist\AgentBusUI.exe` и `dist\AgentBus.exe`.  
Для воркеров по-прежнему нужны Ollama/Aider в системе (exe — оболочка UI/CLI).

## Политика

- Чат на ПК — главный канал задач.
- Телефонный file-bus — опция в настройках.
- `local_only` в policy — без облака.
