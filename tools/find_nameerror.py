# tools/find_nameerror.py
import os, re

root = r"C:\Projects\Revive"
pattern = re.compile(r'(?<!def )\bself\b')  # 'self' вне сигнатур def

for base, dirs, files in os.walk(root):
    if "venv" in dirs:  # исключаем venv
        dirs.remove("venv")
    for f in files:
        if f.endswith(".py"):
            p = os.path.join(base, f)
            try:
                with open(p, "r", encoding="utf-8") as fh:
                    for i, line in enumerate(fh, 1):
                        if pattern.search(line) and "class " not in line:
                            print(f"{p}:{i}: {line.strip()}")
            except Exception:
                pass
