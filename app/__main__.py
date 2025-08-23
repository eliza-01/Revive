# app/__main__.py
from __future__ import annotations
import os, sys
from .launcher_bootstrap import launch_universal

PROJ_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

def _detect_version() -> str:
    if len(sys.argv) > 1:
        return sys.argv[1]
    try:
        with open(os.path.join(PROJ_ROOT, "documents", "latest_version.txt"), "r", encoding="utf-8") as f:
            v = (f.read() or "").strip()
            if v:
                return v
    except Exception:
        pass
    return "dev"

if __name__ == "__main__":
    launch_universal(_detect_version())
