# -*- coding: utf-8 -*-
"""Skills registry facade — re-exports SkillRegistry from monolithic module.

Sprint C: gradual split. Call sites can `from skills.registry import SkillRegistry`.
"""
from __future__ import annotations

from skills.skills import SkillRegistry, SKILLS  # type: ignore

__all__ = ["SkillRegistry", "SKILLS"]
