# Canonical files

## Runtime
| File | file_id |
|------|---------|
| runtime_ops.py | `1B7N6vKCn6TV6o7rBaH_HIZH-k4OYA3K-` |
| recovery_plan_hook.py | `1iERjF_Drws5R9FtYODmYbwbYMeCpMr3s` |
| recovery_decision.py | `1SM7caLw_SwaLWyxa2Dul4Fc4xDq7TMNO` |
| recovery_mechanism.py | `1cgqvXWIs9hpYnUclsappjVA348DxLbmK` |
| worker_execution.py | `1QAf1ZYwTwqtZFdDtR8SyoPUJ8hz7Gl7m` |
| execution_evidence.py | `18dnF005ZbiRVK_wc6_bhNoaYIAWRd0l7` |
| reclaim.py | `1YCiuwSEElchstilyw15BaqV8Qtf4bCXV` |
| rp_lifecycle / rp_llm / rp_verify | prior ids |

## Product / UI
| File | file_id |
|------|---------|
| product_surface.py | `191SwyKDDpFfj9FwVTQEoPXE21qjoesgL` |
| chat_panel.py | `1Mw2Mz4ZVQ7TiTgcADFA___n5-2KclngH` |
| chat_recovery_bridge.py | `1XYL7ShZgdCgywc0RNumlfo45cH6EtwPS` |

## ERROR path
Chat ERROR → format_error_row → handle_error_recovery → plan replan if action=replan
**enqueued always false**
