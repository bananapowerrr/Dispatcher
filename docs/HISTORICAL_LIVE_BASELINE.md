# HISTORICAL LIVE BASELINE AUDIT (read-only)

**Дата:** 2026-09-20  
**Источники:** [Prediction-Analyzer@ffb59e7](https://github.com/bananapowerrr/Prediction-Analyzer/commit/ffb59e765eb9dcf3baa6a1080acb599cfe641366), текущий AgentBus (`config/workers.yaml`, `src/core/executor.py`, `src/core/config.py`, `rp_llm.py`)  
**Режим:** только аудит. Runtime/UI/AI **не** изменялись.

---

## 1. Вердикт

> Старый execution path **доказанно работал** (август 2026): Dispatcher → Aider 0.86.2 → `ollama_chat/qwen2.5-coder:7b` → реальные файлы.  
> Текущий AgentBus **сохраняет ту же CLI-формулу Aider** в `aider_local`.  
> Риск не «умеем ли мы Aider», а **новые обёртки** (FSM, intake, context injection, verify, gitops) не ломают доставку message/files/cwd и не объявляют DONE без diff+verify.

---

## 2. Исторический baseline (Prediction-Analyzer)

### Commit `ffb59e7` (2026-08-25) — «Aider pipeline OK»

Из `.aider.chat.history.md` в коммите:

| Поле | Значение |
|------|----------|
| Aider | **v0.86.2** |
| Binary | `C:\Users\user\AppData\Local\Programs\Python\Python312\Scripts\aider` |
| Flags | `--yes --model ollama_chat/qwen2.5-coder:7b --no-auto-commits --message …` |
| Model | **`ollama_chat/qwen2.5-coder:7b`** (не `ollama/…`) |
| CWD / project | `D:\Workspace\desktop-tutorial` |
| AgentBus path | `G:\Мой диск\AgentBus` — **явно исключён** из workspace |
| Git policy | **запрет** git add/commit/push (делает диспетчер после проверки) |
| Task | создать `test_aider.txt` с строкой `Aider pipeline OK` |
| Результат | `Applied edit to test_aider.txt` · файл в коммите |
| Git repo at start | `Git repo: none` (в том прогоне) |
| Repo-map | disabled |

Message pattern (исторический):

```
Контекст: проект `desktop-tutorial`. Корень git: D:\Workspace\desktop-tutorial.
Работай ТОЛЬКО внутри этой папки. AgentBus на G:\… — НЕ часть проекта.
НЕ выполняй git add/commit/push — это сделает диспетчер после проверки.
Задача: Создай файл test_aider.txt …
```

### Связанные commits

- `188f6b3` — удаление aider history из репо (артефакт был временным, рабочим).
- `065ae6a` — более поздний trace: Git repo с файлами, repo-map, правки вроде `core/models.py`, та же модель `ollama_chat/qwen2.5-coder:7b`.

### Prediction-Analyzer сам

- Локальный Ollama: `LOCAL_OLLAMA_BASE_URL=http://localhost:11434`, judge `qwen2.5-coder:7b` — тот же стек моделей.

---

## 3. Текущий path (AgentBus)

### Worker `aider_local` (`config/workers.yaml`)

```yaml
name: aider_local
harness: aider
provider: ollama
model: ollama_chat/qwen2.5-coder:7b
command: "{aider} {yes} --model {aider_model} --no-auto-commits --no-pretty --no-stream {files} --message {message}"
timeout: 900
```

Default model (`src/core/config.py`):

```python
AIDER_MODEL = os.getenv('AIDER_MODEL', 'ollama_chat/qwen2.5-coder:7b')
```

### Executor

- Подстановка `{aider}`, `{yes}`, `{aider_model}`, `{files}`, `{message}`.
- `OLLAMA_API_BASE` default `http://127.0.0.1:11434`.
- Preflight probe `/api/tags`, deps repair для Aider/GitPython.
- Timeout + process kill, PIPE stdout/stderr.

### Runtime (новое относительно августа)

```
Chat/UI → intake (fail-closed) → LocalQueue
  → CLAIM → router → aider_local
  → executor subprocess
  → filesystem / git status
  → VerificationEngine
  → DONE only if verify OK
  → Plan terminal hook (task_id)
```

Контекст сообщения собирается в `rp_llm` (`_llm_build_worker_message`, ContextBuilder) — **аналог** исторического «Контекст: проект… НЕ git commit».

---

## 4. Сравнение этап за этапом

| Этап | Старый (PA / монолит) | Новый (AgentBus) | Риск регрессии |
|------|----------------------|------------------|----------------|
| Task source | file-bus / auto message | Chat UI + LocalQueue + file-bus | Низкий, если intake не режет простой текст |
| Worker select | прямой aider | router → `aider_local` | Средний: router может выбрать cloud/opencode |
| Aider binary | Scripts\aider | `{aider}` / `AIDER_PATH` | **Средний:** PATH на новой машине |
| Model string | `ollama_chat/qwen2.5-coder:7b` | **то же** default | Низкий |
| Flags | `--yes --no-auto-commits --message` | + `--no-pretty --no-stream` | Низкий (совместимо) |
| Message | длинный контекст + задача | context budget + MEMORY + tools block | **Средний:** слишком жирный контекст для 7B |
| Files argv | опционально | `{files}` из task.files | **Средний:** пустой files → aider без фокуса |
| CWD | project root | project root в executor | **Высокий**, если cwd = AgentBus root |
| OLLAMA_API_BASE | implicit/local | explicit 127.0.0.1:11434 | Низкий |
| Git commits | запрещены в prompt | `--no-auto-commits` + gitops после verify | Низкий / лучше |
| Success signal | «Applied edit» + file exists | verify ladder + FSM DONE | **Высокий**, если verify жёстче/слабее |
| DONE authority | диспетчер после проверки | **только** verify gate | Контракт правильный; не ломать |

---

## 5. Потенциальные точки регрессии (P0 checklist на ПК)

1. **CWD** — subprocess cwd == sandbox project, не каталог AgentBus.  
2. **Router** — для smoke принудительно/ожидаемо `aider_local`, не cloud.  
3. **Message size** — не раздуть 7B до «lost in the middle».  
4. **`{files}`** — для LIVE-001 передать целевые пути или явно пустой список как в PA.  
5. **`AIDER_PATH` / venv** — тот же aider, что в истории (0.86.x+).  
6. **OLLAMA up + model pulled** — `qwen2.5-coder:7b`.  
7. **Verify после diff** — файл появился, но status ERROR из-за пустого pytest → не путать с «Aider не работает».  
8. **Git dirty / branch policy** — preflight stash/branch не блокирует простой create file.

---

## 6. Рекомендуемый первый live smoke (как исторический)

Повторить **смысл** `ffb59e7`, не абстрактный «refactor all»:

```
Создай файл test_aider.txt в корне проекта с одной строкой:
Aider pipeline OK
Больше ничего не меняй. Не делай git commit.
```

Ожидание:

```
CLAIM → PROCESSING → aider_local → Applied edit / file exists
→ VERIFY (syntax/policy) → DONE
```

Evidence: `.agentbus/runs/<id>/summary.md` + `git status` + содержимое `test_aider.txt`.

Если **файл есть**, а status ≠ DONE → баг в **VERIFY/RUNTIME**, не в Aider.  
Если **файла нет** → баг в **WORKER/EXECUTOR/CWD/model**.

---

## 7. Что НЕ делать по результатам аудита

- Не переписывать executor «на всякий случай».  
- Не менять model prefix на `ollama/` без live-причины (`ollama_chat/` — исторически рабочий).  
- Не добавлять AI-фичи до прохождения этого одного smoke.

---

## 8. Готовность

| Артефакт | Статус |
|----------|:------:|
| Historical baseline documented | ✅ |
| Current aider_local matches CLI shape | ✅ |
| Regression risk table | ✅ |
| First live smoke defined | ✅ |
| Code changes | ❌ none (freeze) |
