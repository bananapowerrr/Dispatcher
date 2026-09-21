# Canonical — R1 Terminal Path

| File | file_id |
|------|---------|
| terminal_path.py | `1HMyrwLy_H8q0FJMN2IWqLABa8VcFiwEG` |
| runtime_ops.py | `1ynpEyraRuXYmEP4RoXbCnkdH-UWxhohZ` |
| rp_lifecycle.py | `1W3sK7ZczT8uyq8Vge1Fg4JIuQmsd2KkG` |
| rp_llm.py | `1MPspRgYdhmpoFzl9gBv7_W6bzkI-8c0a` |

## R1 contract

`finish_task(task, state, result)` →
1. enforce_done_contract (DONE without verify → ERROR)
2. `_save` + evidence
3. `bus.move` processing → done|errors|deferred
4. queue.finish / queue.terminal
5. `_emit` + log

FSM vocabulary unchanged: PENDING→CLAIMED→PROCESSING→VERIFYING→DONE|ERROR|DEFERRED
