# tools/list.py
# Python 3.10+; запуск:  python tools/list.py  --root .  --out tree.txt  --list files.txt  --json files.json

# python tools/list.py --root . --out tree.txt --list files.txt --json files.json

import os
import sys
import fnmatch
import argparse
import json
from pathlib import Path
from typing import Iterable, List, Tuple

DEFAULT_IGNORES = [
    ".git", ".hg", ".svn",
    "__pycache__", ".pytest_cache", ".mypy_cache",
    "venv", ".venv", "env", ".env",
    "build", "dist", "_tmp", ".idea", ".vscode",
    "*.pyc", "*.pyo", "*.pyd", "*.orig",
    "*.log", "*.tmp", "_archive",
]

def parse_args():
    p = argparse.ArgumentParser(description="Сделать список всех файлов проекта и древо каталогов.")
    p.add_argument("--root", default=".", help="Корень проекта (по умолчанию: текущая папка).")
    p.add_argument("--out", default="tree.txt", help="Файл для ASCII-дерева.")
    p.add_argument("--list", dest="list_out", default="files.txt", help="Файл для плоского списка путей.")
    p.add_argument("--json", dest="json_out", default="files.json", help="Файл для JSON-структуры.")
    p.add_argument("--max-depth", type=int, default=0, help="Ограничить глубину дерева (0 = без ограничений).")
    p.add_argument("--ignore", action="append", default=[], help="Паттерн(ы) игнора (можно указывать несколько раз).")
    return p.parse_args()

def _split_patterns(extra: List[str]) -> List[str]:
    out = []
    for s in extra:
        for token in s.split(";"):
            t = token.strip()
            if t:
                out.append(t)
    return out

def should_ignore(path: Path, patterns: List[str]) -> bool:
    # игнор по любому компоненту пути или по целому относительному пути
    rel = str(path).replace("\\", "/")
    parts = rel.split("/")
    for pat in patterns:
        if fnmatch.fnmatch(rel, pat):
            return True
        for part in parts:
            if fnmatch.fnmatch(part, pat):
                return True
    return False

def natural_sort_key(name: str):
    import re
    return [int(text) if text.isdigit() else text.lower() for text in re.split(r"(\d+)", name)]

def walk_tree(root: Path, patterns: List[str], max_depth: int = 0):
    root = root.resolve()
    R = len(str(root))
    def _rel(p: Path) -> str:
        s = str(p)[R+1:] if str(p).startswith(str(root)) else str(p)
        return s.replace("\\", "/")

    dirs = []
    files = []

    for dirpath, dirnames, filenames in os.walk(root):
        dpath = Path(dirpath)
        # фильтруем dirnames in-place, чтобы os.walk не заходил внутрь игнора
        dirnames[:] = [d for d in dirnames if not should_ignore(dpath / d, patterns)]
        dirnames.sort(key=natural_sort_key)

        # ограничение глубины
        if max_depth > 0:
            depth = len(_rel(dpath).split("/")) if _rel(dpath) else 0
            if depth >= max_depth:
                dirnames[:] = []  # не углубляемся дальше

        # директории
        if dpath != root:
            dirs.append(_rel(dpath))

        # файлы
        for fn in sorted(filenames, key=natural_sort_key):
            p = dpath / fn
            if should_ignore(p, patterns):
                continue
            files.append(_rel(p))

    return dirs, files

def draw_tree(root: Path, dirs: List[str], files: List[str]) -> str:
    # построим структуру каталогов
    tree = {"name": root.name, "children": {}, "files": []}

    def insert_path(container, rel_parts: List[str], is_file: bool):
        if not rel_parts:
            return
        head = rel_parts[0]
        if len(rel_parts) == 1 and is_file:
            container.setdefault("files", []).append(head)
            return
        children = container.setdefault("children", {})
        node = children.setdefault(head, {"name": head, "children": {}, "files": []})
        insert_path(node, rel_parts[1:], is_file)

    for d in dirs:
        parts = d.split("/") if d else []
        if parts:
            insert_path(tree, parts, is_file=False)
    for f in files:
        parts = f.split("/") if f else []
        if parts:
            insert_path(tree, parts, is_file=True)

    # печать ASCII
    lines: List[str] = [root.name]

    def render(node, prefix=""):
        # печатаем подпапки
        keys = sorted(node.get("children", {}).keys(), key=natural_sort_key)
        total = len(keys) + len(node.get("files", []))
        idx = 0

        for k in keys:
            idx += 1
            last = (idx == total and len(node.get("files", [])) == 0)
            branch = "└── " if last else "├── "
            lines.append(prefix + branch + k)
            new_prefix = prefix + ("    " if last else "│   ")
            render(node["children"][k], new_prefix)

        # файлы
        files_sorted = sorted(node.get("files", []), key=natural_sort_key)
        for i, fname in enumerate(files_sorted, 1):
            last = (idx + i == total)
            branch = "└── " if last else "├── "
            lines.append(prefix + branch + fname)

    render(tree, "")
    return "\n".join(lines)

def main():
    args = parse_args()
    root = Path(args.root).resolve()
    patterns = DEFAULT_IGNORES + _split_patterns(args.ignore)

    if not root.exists():
        print(f"[E] root not found: {root}", file=sys.stderr)
        sys.exit(2)

    dirs, files = walk_tree(root, patterns, max_depth=args.max_depth)

    # ASCII tree
    ascii_tree = draw_tree(root, dirs, files)
    Path(args.out).write_text(ascii_tree, encoding="utf-8")

    # flat list
    Path(args.list_out).write_text("\n".join(files), encoding="utf-8")

    # JSON
    payload = {
        "root": str(root),
        "count_dirs": len(dirs),
        "count_files": len(files),
        "files": files,
        "ignores": patterns,
    }
    Path(args.json_out).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    # краткий вывод
    print(f"[OK] tree -> {args.out}")
    print(f"[OK] list -> {args.list_out}  (files: {len(files)})")
    print(f"[OK] json -> {args.json_out}")

if __name__ == "__main__":
    main()
