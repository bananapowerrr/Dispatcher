# Offline hardening — 2026-09-13 (Drive)

## Done this session

### P0 Security intake (fail-closed)
- `src/core/task_contract.py` → `normalize_task` вызывает `safety.security.validate_paths/commands/message`
- `src/core/tasks.py` → `Task.from_dict` **всегда** прогоняет `security_validate_task` (даже при `strict=False`)
- Обход через «нестрогий» intake закрыт
- Тесты: `tests/test_security_intake.py`

### P0 Executor soft_log
- `src/core/executor.py` → `_soft_log()` вместо `except Exception: pass`
- Логируются: kill_tree, ollama_alive, pipe_reader, on_line, proc.wait, native_fallback, prefer_native

## Not done (freeze for live)
- New AI features / parallel > 1 / Box as primary write target

## Next offline (optional polish)
- Cross-contract audit FSM → Worker → DONE
- Config consistency docs
- Full pytest when on machine
