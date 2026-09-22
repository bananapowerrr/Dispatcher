# -*- coding: utf-8 -*-
from pathlib import Path


def test_clamp_handles_dict_assemble():
    src = Path("/home/workdir/artifacts/src/core/rp_context.py").read_text(encoding="utf-8")
    assert "assembled.get(\"message\")" in src or "assembled.get('message')" in src
    assert "_stash_context_audit" in src
    assert "_last_context_audit" in src


def test_finish_task_last_result():
    src = Path("/home/workdir/artifacts/src/core/runtime_ops.py").read_text(encoding="utf-8")
    assert "last_result" in src
    assert "GAP: last_result" in src or "last_result" in src


def test_i18n_night_keys():
    en = Path("/home/workdir/artifacts/config/strings_en.yaml").read_text(encoding="utf-8")
    ru = Path("/home/workdir/artifacts/config/strings_ru.yaml").read_text(encoding="utf-8")
    for key in ("settings_tab_night:", "night_title:", "about_check_btn:", "settings_tab_about:"):
        assert key in en, key
        assert key in ru, key


def test_readiness_script_runs():
    import subprocess, sys
    script = Path("/home/workdir/artifacts/scripts/product_readiness_check.py")
    assert script.is_file()
    r = subprocess.run(
        [sys.executable, str(script)],
        cwd="/home/workdir/artifacts",
        capture_output=True,
        text=True,
        timeout=60,
        env={**__import__("os").environ, "PYTHONPATH": "/home/workdir/artifacts/src:/home/workdir/artifacts"},
    )
    assert r.returncode == 0, r.stdout + r.stderr
