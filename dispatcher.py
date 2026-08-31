# -*- coding: utf-8 -*-
"""AgentBus Dispatcher — точка запуска (модули лежат в корне проекта)."""
from __future__ import annotations
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

if __name__ == "__main__":
    try:
        from runtime import main
        main()
    except KeyboardInterrupt:
        print("\nостановлено вручную")
    except Exception:
        txt = traceback.format_exc()
        print(txt)
        try:
            (ROOT / "crash.log").write_text(txt, encoding="utf-8")
        except OSError:
            pass
        sys.exit(1)
