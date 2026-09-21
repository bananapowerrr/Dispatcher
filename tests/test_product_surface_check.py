# -*- coding: utf-8 -*-
from pathlib import Path
import runpy
import sys

def test_product_surface_script_exists_and_runs():
    roots = [
        Path(__file__).resolve().parents[1] / "scripts" / "product_surface_check.py",
        Path("/home/workdir/artifacts/scripts/product_surface_check.py"),
    ]
    script = next(p for p in roots if p.is_file())
    # ensure artifacts ui on path
    art = Path("/home/workdir/artifacts")
    sys.path.insert(0, str(art))
    sys.path.insert(0, str(art / "src"))
    ns = runpy.run_path(str(script))
    rc = ns["main"]()
    assert rc == 0
