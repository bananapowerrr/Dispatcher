# -*- coding: utf-8 -*-
"""Core: runtime, FSM, intake, workers.

Базовый слой. Не импортирует app/ui: иначе core -> app -> core, и любой
`import core.<что-то>` поднимал бы весь сервисный слой. Раньше здесь был
побайтовой копией app/__init__.py с реэкспортом ProjectService и прочих,
чем никто не пользовался. Сервисы для UI берутся из app.
"""
