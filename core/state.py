# -*- coding: utf-8 -*-
"""Process-global mutable state."""
from __future__ import annotations

import datetime
import os
import time
from typing import Dict, Optional, Tuple

SESSION_ID = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

def _logs_dir() -> str:
    drive = os.environ.get("AGENTBUS_DRIVE", r"G:\Мой диск\AgentBus")
    return os.path.join(drive, "channels", "gpt", "logs")

SESSION_LOG = os.path.join(_logs_dir(), f"session_{SESSION_ID}.md")
DISPATCHER_LOG = os.path.join(_logs_dir(), "dispatcher.log")

LAST_BEAT = time.time()
FAIL_STREAK = 0
TASKS_DONE_CYCLE = 0
LAST_CLEANUP = 0.0
LAST_SUPABASE_REQUEUE = 0.0
LAST_SUPABASE_TOUCH = 0.0
CLOUD_RATE_LIMIT_UNTIL = 0.0
SUPABASE_COOLDOWN_UNTIL = 0.0
CURRENT_SUPABASE_TASK_ID: Optional[str] = None
SHUTTING_DOWN = False
_last_gemini_poll = 0.0
_last_supabase_poll = 0.0
_repo_tree_cache: Dict[str, Tuple[float, set]] = {}
LAST_ERRORS_ROTATE = 0.0
ENV_FILE_LOADED: Optional[str] = None
