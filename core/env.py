# -*- coding: utf-8 -*-
"""Load .env without third-party packages."""
from __future__ import annotations

import os
import re
from typing import List, Optional, Tuple

def _parse_dotenv_line(line: str) -> Optional[Tuple[str, str]]:
    line = line.strip()
    if not line or line.startswith("#"):
        return None
    if line.startswith("export "):
        line = line[7:].lstrip()
    if "=" not in line:
        return None
    key, value = line.split("=", 1)
    key = key.strip()
    value = value.strip()
    if not key:
        return None
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        value = value[1:-1]
    else:
        value = re.sub(r"\s+#.*$", "", value).strip()
    return key, value

def load_dotenv() -> Optional[str]:
    candidates: List[str] = []
    explicit = os.getenv("AGENTBUS_ENV_FILE", "").strip()
    if explicit:
        candidates.append(explicit)
    here = os.path.dirname(os.path.abspath(__file__))
    agentbus = os.path.dirname(here)
    candidates.append(os.path.join(agentbus, ".env"))
    candidates.append(os.path.join(os.getcwd(), ".env"))
    drive = os.environ.get("AGENTBUS_DRIVE", r"G:\Мой диск\AgentBus")
    candidates.append(os.path.join(drive, ".env"))
    loaded = None
    for path in candidates:
        if not path or not os.path.isfile(path):
            continue
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                for raw in f:
                    parsed = _parse_dotenv_line(raw)
                    if not parsed:
                        continue
                    k, v = parsed
                    if k not in os.environ:
                        os.environ[k] = v
            loaded = path
            break
        except OSError:
            continue
    return loaded
