# Plugin SDK (кратко)

AgentBus расширяется **без правки ядра**.

## 1. Feature plugins (встроенные модули)

Реестр: `src/core/plugin_registry.py`  
Включение: `config/feature_flags.yaml` или `AGENTBUS_FEATURE_<NAME>=0|1`.

```python
from core.plugin_registry import load, soft_call
mod = load("session_memory")  # None если выключено
```

Критичное ядро (bus, runtime, router, executor) **не** отключается флагами.

## 2. User plugins (`plugins/*.py`)

```bash
python scripts/install_plugin.py path/to/my_plugin.py --enable
```

Минимальный шаблон:

```python
PLUGIN = {
    "name": "hello",
    "version": "0.1",
    "description": "Пример",
}

def on_task_done(task: dict, result: dict) -> None:
    """Опциональный хук после DONE (если extensions загружают)."""
    pass
```

См. `plugins/example_hello.py`.

## 3. Рецепты

Не код, а JSON-сценарии: `recipes/*.json` + UI вкладка «Рецепты».

## 4. Backends

`config/adapters.yaml` + `core.backend` / `native_backend` — смена Ollama ↔ LM Studio без переписывания runtime.
