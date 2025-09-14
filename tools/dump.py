# tools/dump.py
# usage: python tools/dump.py --root . --out collected --sections A,B,C,D,E,F,G,H,J,K,L
from __future__ import annotations
import argparse, sys, os, io
from pathlib import Path
from typing import Iterable, Tuple, List, Dict

# ------------ НАСТРОЙКИ ФИЛЬТРА ФАЙЛОВ ------------
TEXT_EXTS = {
    ".py", ".pyi",
    ".json",
    ".js", ".ts",
    ".html", ".htm",
    ".css",
    ".md", ".txt",
    ".toml", ".ini", ".cfg",
    ".yml", ".yaml",
    ".bat", ".sh", ".ps1",
    ".spec",
}
BINARY_EXTS = {
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".bmp", ".webp",
    ".exe", ".dll", ".pyd", ".so", ".dylib",
    ".zip", ".7z", ".rar", ".gz", ".xz", ".bz2",
    ".ttf", ".otf", ".woff", ".woff2",
}

def _is_text_file(p: Path) -> bool:
    suf = p.suffix.lower()
    if suf in BINARY_EXTS:
        return False
    if suf in TEXT_EXTS:
        return True
    return False

# ------------ РАЗДЕЛЫ (ТОЛЬКО САМОЕ ВАЖНОЕ) ------------
# ВАЖНО: из core/servers исключаем папки boh и l2mad; из _archive берём только checks и core/{features,runtime}
SECTIONS: Dict[str, List[str]] = {
    # A) Core I/O и Windows-обвязка
    "A": [
        "core/connection.py",
        "core/connection_test.py",
        "core/os/win/window.py",
        "core/os/win/mouse.py",
        "core/logging_setup.py",
        "core/updater.py",
    ],

    # B) Vision
    "B": [
        "core/vision/matching.py",
        "core/vision/utils/colors.py",
        "core/vision/win32/gdi_backend.py",
        "core/vision/capture/gdi.py",
        "core/vision/capture/window_bgr_capture.py",
        "core/vision/matching/template_matcher.py",
    ],

    # C) Arduino
    "C": [
        "core/arduino/safe_serial.py",
        "core/arduino/send_command.py",
        "core/arduino/send_safe.py",
        "core/arduino/serial_port.py",
    ],

    # D) Orchestrators (актуальные)
    "D": [
        "core/orchestrators/rules_base.py",
        "core/orchestrators/runtime.py",
        "core/orchestrators/snapshot.py",
    ],

    # E) Autofarm engine (актуальная структура core/engines/autofarm/*)
    "E": [
        "core/engines/autofarm/__init__.py",
        "core/engines/autofarm/service.py",
        "core/engines/autofarm/runner.py",
        "core/engines/autofarm/skill_repo.py",
        "core/engines/autofarm/zone_repo.py",
        "core/engines/autofarm/common/*.py",
        "core/engines/autofarm/common/**/*.json",
        "core/engines/autofarm/server/*/engine.py",
        "core/engines/autofarm/server/*/*.py",
        "core/engines/autofarm/server/*/**/*.json",
    ],

    # F) Launcher (новая структура)
    "F": [
        "app/launcher/base.py",
        "app/launcher/main.py",
        "app/launcher/wiring.py",
        "app/launcher/sections/*.py",
    ],

    # G) WebUI (HTML/JS — без бинарных ассетов)
    "G": [
        "app/webui/index.html",
        "app/webui/js/*.js",
        "app/webui/hud.html",
    ],

    # H) Core/Servers (только базовые файлы, БЕЗ boh и l2mad)
    "H": [
        "core/servers/__init__.py",
        "core/servers/base_config.py",
        "core/servers/registry.py",
    ],

    # J) _archive/checks (только важное)
    "J": [
        "_archive/checks/charged.py",
    ],

    # K) _archive/core/features (только модули фич)
    "K": [
        "_archive/core/features/__init__.py",
        "_archive/core/features/afterbuff_macros.py",
        "_archive/core/features/buff_after_respawn.py",
        "_archive/core/features/dashboard_reset.py",
        "_archive/core/features/flow_actions.py",
        "_archive/core/features/post_teleport_row.py",
        "_archive/core/features/restart_manager.py",
        "_archive/core/features/to_village.py",
        "_archive/core/features/teleport_after_respawn.py",
        # player_state — берем актуальный из core/engines/player_state (если он есть),
        # а из _archive только при необходимости:
        "_archive/core/features/archive/player_state.py",
    ],

    # L) _archive/core/runtime (ядро флоу: engine/runner/etc)
    "L": [
        "_archive/core/runtime/dashboard_guard.py",
        "_archive/core/runtime/flow_config.py",
        "_archive/core/runtime/flow_engine.py",
        "_archive/core/runtime/flow_ops.py",
        "_archive/core/runtime/flow_runner.py",
        "_archive/core/runtime/poller.py",
        "_archive/core/runtime/state_watcher.py",
    ],

    # M) Player State engine
    "M": [
        "core/engines/player_state/__init__.py",
        "core/engines/player_state/runner.py",
        "core/engines/player_state/watcher.py",
        "core/engines/player_state/server/*/*.py",
        "core/engines/player_state/server/*/**/*.py",
        "core/engines/player_state/server/*/**/*.json",
    ],

    # N) Respawn engine
    "N": [
        "core/engines/respawn/__init__.py",
        "core/engines/respawn/runner.py",
        "core/engines/respawn/server/*/*.py",
        "core/engines/respawn/server/*/**/*.py",
        "core/engines/respawn/server/*/**/*.json",
    ],
}

SECTION_TITLES: Dict[str, str] = {
    "A": "Core I/O & Windows",
    "B": "Vision",
    "C": "Arduino",
    "D": "Orchestrators",
    "E": "Autofarm Engine",
    "F": "Launcher",
    "G": "Web UI",
    "H": "Core Servers (base only)",
    "J": "Archive Checks",
    "K": "Archive Core Features",
    "L": "Archive Core Runtime",
    "M": "Player State Engine",
    "N": "Respawn Engine",
}

OUT_FILENAMES: Dict[str, str] = {
    "F": "1F_launcher.txt",
    "D": "2D_orchestrators.txt",
    "M": "3M_player_state_engine.txt",
    "N": "4N_respawn_engine.txt",
    "L": "5L_archive_runtime.txt",
    "A": "A_core_io_windows.txt",
    "B": "B_vision.txt",
    "C": "C_arduino.txt",
    "E": "E_autofarm_engine.txt",
    "G": "G_webui.txt",
    "H": "H_servers_base.txt",
    "J": "J_archive_checks.txt",
    "K": "K_archive_features.txt",
}

# Дополнительные глобальные исключения путей (строки, которые не должны попадать)
# По условию: из core/servers НЕ брать папки boh и l2mad
EXCLUDE_PATH_SUBSTR = [
    "core/servers/boh/",
    "core/servers/l2mad/",
]

def _excluded(p: Path, root: Path) -> bool:
    rel = p.relative_to(root).as_posix()
    for sub in EXCLUDE_PATH_SUBSTR:
        if rel.startswith(sub):
            return True
    return False

# ------------ СБОРЩИК ------------
def _iter_matches(root: Path, patterns: Iterable[str]) -> List[Path]:
    seen: set[Path] = set()
    out: List[Path] = []
    for pat in patterns:
        paths = sorted(root.glob(pat), key=lambda p: str(p).lower())
        if not paths and ("*" not in pat and "?" not in pat and "**" not in pat):
            out.append(root / f"__MISSING__::{pat}")
            continue
        for p in paths:
            if p.is_file() and _is_text_file(p):
                if _excluded(p, root):
                    continue
                rp = p.resolve()
                if rp not in seen:
                    seen.add(rp)
                    out.append(p)
    return out

def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return f"# !!! ERROR reading {path}: {e}\n"

def build_section(root: Path, out_dir: Path, letter: str) -> Tuple[int,int,List[str]]:
    patterns = SECTIONS[letter]
    files = _iter_matches(root, patterns)

    dst = out_dir / OUT_FILENAMES[letter]
    dst.parent.mkdir(parents=True, exist_ok=True)

    included = 0
    missing = 0
    manifest_entries: List[str] = []

    with io.open(dst, "w", encoding="utf-8", newline="\n") as w:
        title = SECTION_TITLES.get(letter, letter)
        w.write(f"# === SECTION {letter}: {title} ===\n# root: {root}\n\n")
        for p in files:
            if p.name.startswith("__MISSING__::"):
                missing += 1
                miss = str(p.name).split("::",1)[1]
                w.write(f"# --- MISSING: {miss}\n\n")
                manifest_entries.append(f"{letter}\tMISSING\t{miss}")
                continue
            rel = p.relative_to(root)
            w.write(f"# --- BEGIN FILE: {rel.as_posix()} ---\n")
            content = _read_text(p)
            w.write(content)
            if not content.endswith("\n"):
                w.write("\n")
            w.write(f"# --- END FILE: {rel.as_posix()} ---\n\n")
            included += 1
            manifest_entries.append(f"{letter}\tINCLUDE\t{rel.as_posix()}")

    return included, missing, manifest_entries

def main():
    ap = argparse.ArgumentParser(description="Собрать файлы по разделам в текстовые дампы + единый манифест.")
    ap.add_argument("--root", default=".", help="корень проекта")
    ap.add_argument("--out", default="collected", help="каталог вывода")
    ap.add_argument("--sections", default="A,B,C,D,E,M,N,F,G,H,J,K,L", help="какие разделы собирать, через запятую")
    ap.add_argument("--manifest-name", dest="manifest_name", default="manifest.txt", help="имя файла единого манифеста")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    out_dir = Path(args.out).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    all_entries_by_section: Dict[str, List[str]] = {}
    letters = [s.strip().upper() for s in args.sections.split(",") if s.strip()]
    for l in letters:
        if l not in SECTIONS:
            print(f"[skip] неизвестный раздел: {l}")
            continue
        inc, miss, entries = build_section(root, out_dir, l)
        print(f"[{l}] written -> {OUT_FILENAMES[l]}  files: {inc}  missing: {miss}")
        all_entries_by_section.setdefault(l, []).extend(entries)

    # ЕДИНЫЙ МАНИФЕСТ (с разделителями по секторам)
    manifest_path = out_dir / args.manifest_name
    with io.open(manifest_path, "w", encoding="utf-8", newline="\n") as mf:
        mf.write("# section\tstatus\teleportath\n")
        for l in letters:
            if l not in all_entries_by_section:
                continue
            title = SECTION_TITLES.get(l, l)
            mf.write(f"\n# --- SECTION {l}: {title} ---\n")
            for line in all_entries_by_section[l]:
                mf.write(line + "\n")

    print(f"[done] outeleportut: {out_dir}")
    print(f"[manifest] {manifest_path.name}: {sum(len(v) for v in all_entries_by_section.values())} entries")

if __name__ == "__main__":
    sys.exit(main())
