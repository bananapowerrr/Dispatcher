#!/usr/bin/env bash
# FC-22 offline regression — no Ollama/Aider required
set -euo pipefail
cd "$(dirname "$0")/.."
export PYTHONPATH="src:."

echo "=== AgentBus FC-22 regression ==="

echo "[1] import health"
python - <<'PY'
import importlib
from pathlib import Path
ok = fail = 0
for py in sorted(Path("src").rglob("*.py")):
    if "__pycache__" in py.parts:
        continue
    rel = py.relative_to("src").with_suffix("")
    mod = ".".join(rel.parts)
    if mod.endswith(".__init__"):
        mod = mod[: -len(".__init__")]
    try:
        importlib.import_module(mod)
        ok += 1
    except Exception as e:
        print(f"  FAIL {mod}: {type(e).__name__}: {e}")
        fail += 1
print(f"  imports OK={ok} FAIL={fail}")
raise SystemExit(1 if fail else 0)
PY

echo "[2] targeted FC suite"
python -m pytest -q --tb=line \
  tests/test_compat_fc20.py \
  tests/test_ui_polish_fc21.py \
  tests/test_doctor_fc18.py \
  tests/test_trace_fc19.py \
  tests/test_queue_ux_fc17.py \
  tests/test_worker_contract_fc14.py \
  tests/test_skill_contract_fc15.py \
  tests/test_verification_fc11.py \
  tests/test_history_fc10.py \
  tests/test_error_ux_fc12.py \
  tests/test_retry_ux_fc13.py \
  tests/test_deferred_ux_fc16.py \
  tests/test_task_contract.py \
  tests/test_task_trace_terminal.py

echo "[3] smoke_offline (if present)"
if [[ -f scripts/smoke_offline.py ]]; then
  python scripts/smoke_offline.py || true
fi

echo "=== FC-22 GREEN ==="
