# -*- coding: utf-8 -*-
"""Application API — façade between UI and core/intelligence.

UI must not import dynamic_queue / living_plan / decision_queue directly.
Use ProjectService, FilesService, TasksService, AgentService, ChangesService.
"""
from app.project_service import ProjectService
from app.files_service import FilesService
from app.tasks_service import TasksService
from app.agent_service import AgentService
from app.changes_service import ChangesService

__all__ = [
    "ProjectService",
    "FilesService",
    "TasksService",
    "AgentService",
    "ChangesService",
]
