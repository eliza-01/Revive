from __future__ import annotations
import os, sys

def _read_version() -> str:
    env = os.getenv("REVIVE_VERSION")
    if env:
        return env
    try:
        here = os.path.dirname(os.path.abspath(__file__))
        with open(os.path.join(here, "documents", "latest_version.txt"), "r", encoding="utf-8") as f:
            v = (f.read() or "").strip()
            return v or "dev"
    except Exception:
        return "dev"

def main():
    ver = sys.argv[1] if len(sys.argv) > 1 else _read_version()
    from app.launcher_bootstrap import launch_universal
    launch_universal(ver)

if __name__ == "__main__":
    main()
