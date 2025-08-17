#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# tools/dump_tree.py

import os
import sys
import datetime

IGNORED_DIRS = {"venv", ".idea", "_tmp", "__pycache__", ".git", "build"}

def list_dir(path: str):
    try:
        return sorted(os.listdir(path))
    except Exception:
        return []

def is_dir(path: str) -> bool:
    try:
        return os.path.isdir(path)
    except Exception:
        return False

def build_tree(root: str, prefix: str = ""):
    entries = list_dir(root)
    entries = [e for e in entries if e not in IGNORED_DIRS]
    dirs = [e for e in entries if is_dir(os.path.join(root, e))]
    files = [e for e in entries if not is_dir(os.path.join(root, e))]
    entries = sorted(dirs) + sorted(files)

    for i, name in enumerate(entries):
        full = os.path.join(root, name)
        is_last = (i == len(entries) - 1)
        connector = "└── " if is_last else "├── "
        yield f"{prefix}{connector}{name}"
        if is_dir(full) and name not in IGNORED_DIRS:
            new_prefix = f"{prefix}{'    ' if is_last else '│   '}"
            for line in build_tree(full, new_prefix):
                yield line

def main():
    root = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else os.getcwd()
    out_path = os.path.join(root, "PROJECT_STRUCTURE.txt")

    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        f"Root: {root}",
        f"Generated: {now}",
        "",
        os.path.basename(root),
    ]
    lines.extend(build_tree(root))

    with open(out_path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines))

    print(f"Wrote: {out_path}")

if __name__ == "__main__":
    main()
