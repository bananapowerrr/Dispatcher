# -*- coding: utf-8 -*-
"""Skills package — deterministic skills, tools, autopilot, classifiers."""
from __future__ import annotations

# tools first (skills.py depends on ToolRegistry)
from .tools import *  # noqa: F401,F403
from .skills import *  # noqa: F401,F403
try:
    from .skill_learner import *  # noqa: F401,F403
except Exception:
    pass
try:
    from .autopilot import *  # noqa: F401,F403
except Exception:
    pass

try:
    from .custom_loader import load_custom_skills  # noqa: F401
except Exception:
    def load_custom_skills(*a, **k):
        return []
