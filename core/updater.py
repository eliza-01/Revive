# core/updater.py
import os
import sys
import time
from core.logging import console

def get_remote_version() -> str:
    return "0.0.1"

def get_update_changelog() -> str:
    return "• Initial stub changelog\n• Nothing real yet"

def is_newer_version(remote: str, local: str) -> bool:
    def parse(v): return [int(p) for p in v.split(".") if p.isdigit()]
    return parse(remote) > parse(local)

def download_new_exe(remote_version: str, progress_callback):
    for i in range(0, 101, 5):
        time.sleep(0.03)
        progress_callback(i)
    return f"Revive-{remote_version}.exe"

def launch_downloaded_exe_and_exit(exe_name: str):
    console.log(f"[update] would launch: {exe_name}")
    sys.exit(0)
