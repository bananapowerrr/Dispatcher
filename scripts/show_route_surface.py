#!/usr/bin/env python3
"""Print advisory worker route for a message (no Runtime)."""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]
msg = " ".join(sys.argv[1:]) or "fix bug in project"
from app.product_surface import attach_context_preview, doctor_route_snippet

print(doctor_route_snippet(msg))
print("---")
c = attach_context_preview(msg)
print(c.get("chat_line"))
print((c.get("chat_detail") or "")[:400])
