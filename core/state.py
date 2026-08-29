# -*- coding: utf-8 -*-
"""Изменяемое состояние процесса."""
from __future__ import annotations

import datetime
import os
import time
from typing import Dict, Optional, Tuple

from core import config as cfg

SESSION_ID = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
SESSION_LOG = os.path.join(cfg.LOGS, f"session_{SESSION_ID}.md")
DISPATCHER_LOG = os.path.join(cfg.LOGS, "dispatcher.log")

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
