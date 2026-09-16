# Быстрый старт (ПК)

## 1. Зависимости

```bash
pip install -r requirements.txt
pip install -r requirements-ui.txt   # GUI
ollama pull qwen2.5-coder:7b         # или LM Studio :1234
```

## 2. Init + doctor

```bash
python dispatcher.py --init
python dispatcher.py --doctor
```

## 3. Запуск

```bash
python dispatcher.py          # движок
python dispatcher_ui.py       # чат
```

Пишите задачу в чат. Нужен запущенный диспетчер.

## 4. Рецепты

В UI: **Рецепт** → Запустить  
CLI: `python dispatcher.py --recipe tests --target src/foo.py`

## 5. Политика

Настройки → **Политика**: `local_only` (без облака) / `balanced` / …

## 6. Телефон (не обязательно)

Вкладка **Телефон** → включить `phone_filebus`.  
См. `docs/CHANNELS_RU.md`.
