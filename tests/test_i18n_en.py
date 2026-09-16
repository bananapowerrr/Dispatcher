# -*- coding: utf-8 -*-
from __future__ import annotations

import os

from i18n import load_strings, t


def test_en_strings(monkeypatch):
    monkeypatch.setenv("AGENTBUS_LANG", "en")
    load_strings.cache_clear = getattr(load_strings, "cache_clear", lambda: None)
    # clear module cache
    import i18n
    i18n._cache.clear()
    assert t("tab_logs", default="Logs") in ("Logs", "Логи")  # en preferred
    data = load_strings("en")
    assert data.get("send") == "Send"
    assert data.get("settings_tab_workers") == "Workers"
    i18n._cache.clear()
