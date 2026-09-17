# -*- coding: utf-8 -*-
from pathlib import Path

def test_welcome_and_safe_refresh_in_main():
    src = Path("ui/main_window.py").read_text(encoding="utf-8")
    assert "def _welcome_desktop" in src
    assert "def _safe_refresh" in src
    assert "PROFILE_BEGINNER" in src
    assert "self.workers_panel.pack" in src

def test_welcome_i18n_keys():
    ru = Path("config/strings_ru.yaml").read_text(encoding="utf-8")
    en = Path("config/strings_en.yaml").read_text(encoding="utf-8")
    assert "welcome_1" in ru and "welcome_1" in en
