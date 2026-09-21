# Canonical — R3 Recovery Controller

| File | file_id |
|------|---------|
| recovery_controller.py | `1q7knZH4JSef4kbfqraDymOVnAhGr1vk8` |
| runtime_ops.py | `17410JhK2ug2zx0t_FitdIgPApY3nCB0c` |
| product_surface.py | `1FuwZ-Xn5Qg0qjoaDlbrGvELEzV7bB4el` |
| execution_evidence.py | `1J9he25xk-RUNOIgOTSXuf9PtGBz8wgiI` |
| terminal_path.py | `1HMyrwLy_H8q0FJMN2IWqLABa8VcFiwEG` |

## Flow
```
ERROR finish_task
  → run_recovery(apply_plan=False)  # record decision
Chat handle_error_recovery
  → run_recovery(apply_plan=True)   # plan replan if needed
enqueued: always false
```
