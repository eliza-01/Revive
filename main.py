# main.py
import os
import sys
from app import launch_gui

def _base_dir():
    return os.path.dirname(sys.executable if getattr(sys, "frozen", False) else os.path.abspath(__file__))

def get_local_version() -> str:
    env_ver = os.getenv("REVIVE_VERSION")
    if env_ver:
        return env_ver.strip()
    try:
        with open(os.path.join(_base_dir(), "VERSION"), "r", encoding="utf-8") as f:
            v = f.read().strip()
            if v:
                return v
    except Exception:
        pass
    return "0.0.0"

if __name__ == "__main__":
    launch_gui(get_local_version())
