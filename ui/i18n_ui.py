# -*- coding: utf-8 -*-
"""UI-safe i18n wrapper (adds src to path)."""
from __future__ import annotations

from ui.paths import ensure_sys_path

ensure_sys_path()

try:
    from i18n import t
except Exception:  # pragma: no cover
    def t(key: str, default: str | None = None, **kwargs):  # type: ignore[misc]
        text = default if default is not None else key
        if kwargs:
            try:
                return text.format(**kwargs)
            except Exception:
                return text
        return text
