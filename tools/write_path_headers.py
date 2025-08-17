# tools/write_path_headers.py
from __future__ import annotations
import sys, re
from pathlib import Path, PurePosixPath

IGNORED_DIRS = {"venv", ".idea", "_tmp", "__pycache__", ".git", "build"}

ENCODING_RE = re.compile(r"coding[:=]\s*([-\w.]+)")
PATH_HEADER_RE = re.compile(r"^#\s+([A-Za-z0-9_\-./\\]+\.py)\s*$")

def detect_encoding(lines: list[str]) -> str | None:
    # PEP 263: cookie must be on line 1 or 2 (index 0 or 1), possibly after shebang
    rng = lines[:2] if lines else []
    for ln in rng:
        m = ENCODING_RE.search(ln)
        if m:
            return m.group(1)
    return None

def read_text_any(p: Path) -> tuple[str, str]:
    # Try utf-8-sig, then cp1251, then latin-1
    for enc in ("utf-8-sig", "cp1251", "latin-1"):
        try:
            text = p.read_text(encoding=enc)
            return text, enc
        except Exception:
            continue
    # Fallback binary
    data = p.read_bytes()
    return data.decode("utf-8", errors="replace"), "utf-8"

def write_text(p: Path, text: str, enc_hint: str | None):
    enc = enc_hint or "utf-8"
    p.write_text(text, encoding=enc, newline="\n")

def is_ignored(p: Path) -> bool:
    return any(part in IGNORED_DIRS for part in p.parts)

def compute_header(root: Path, file_path: Path) -> str:
    rel_posix = PurePosixPath(file_path.relative_to(root)).as_posix()
    return f"# {rel_posix}"

def place_header(lines: list[str], header: str) -> tuple[list[str], bool]:
    if not lines:
        return [header + "\n"], True

    shebang = lines[0].startswith("#!")
    enc_on_line1 = ENCODING_RE.search(lines[0]) is not None
    enc_on_line2 = len(lines) > 1 and ENCODING_RE.search(lines[1]) is not None

    # If a path-like header already exists in first 3 lines, replace it.
    header_idx = None
    for idx in range(min(3, len(lines))):
        if PATH_HEADER_RE.match(lines[idx].rstrip("\r\n")):
            header_idx = idx
            break

    if header_idx is not None:
        if lines[header_idx].rstrip("\r\n") == header:
            return lines, False
        new_lines = lines[:]
        new_lines[header_idx] = header + "\n"
        return new_lines, True

    # Decide insertion index respecting shebang and encoding cookie rules.
    insert_at = 0
    if shebang:
        # Do not break shebang at first line.
        insert_at = 1
        # If encoding cookie at line 2 (index 1), keep it in first two lines.
        if enc_on_line2:
            insert_at = 2
    else:
        # If encoding cookie at line 1 (index 0), keep it in first two lines.
        if enc_on_line1:
            insert_at = 1

    # If the exact header is already at target spot, no change.
    if insert_at < len(lines) and lines[insert_at].rstrip("\r\n") == header:
        return lines, False

    new_lines = lines[:insert_at] + [header + "\n"] + lines[insert_at:]
    return new_lines, True

def process_file(root: Path, p: Path) -> tuple[bool, str]:
    text, enc_read = read_text_any(p)
    lines = text.splitlines(keepends=False)
    header = compute_header(root, p)
    new_lines, changed = place_header(lines, header)
    if changed:
        enc_cookie = detect_encoding(lines)
        write_text(p, "\n".join(ln.rstrip("\r\n") for ln in new_lines) + ("\n" if new_lines and not new_lines[-1].endswith("\n") else ""), enc_cookie or enc_read)
    return changed, header

def main():
    root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd()
    if not root.exists():
        print(f"[ERR] Root not found: {root}")
        sys.exit(2)
    changed_cnt = 0
    total = 0
    for p in root.rglob("*.py"):
        if is_ignored(p) or any(part.startswith(".") and part != ".git" for part in p.parts if part != p.name):
            continue
        total += 1
        try:
            changed, header = process_file(root, p)
            if changed:
                changed_cnt += 1
                print(f"[UPDATED] {p}  ->  {header}")
            else:
                print(f"[OK]      {p}")
        except Exception as e:
            print(f"[SKIP]    {p}  ({e})")
    print(f"\nDone. {changed_cnt} updated of {total} files.")

if __name__ == "__main__":
    main()
