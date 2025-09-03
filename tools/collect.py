# tools/collect.py
# usage: python tools/collect.py --root . --out collected --sections A,B,C,D,E,F,G,H,I
from __future__ import annotations
import argparse, sys, os, io
from pathlib import Path
from typing import Iterable, Tuple, List

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
    if suf in BINARY_EXTS: return False
    if suf in TEXT_EXTS: return True
    return False

# ------------ РАЗДЕЛЫ (ТОЛЬКО САМОЕ ВАЖНОЕ) ------------
SECTIONS: dict[str, list[str]] = {
    # A) Ядро и I/O
    "A": [
        "core/connection.py",
        "core/connection_test.py",
        "core/checks/charged.py",
        "core/runtime/state_watcher.py",
        "core/runtime/poller.py",
        "core/runtime/flow_engine.py",
        "core/runtime/flow_ops.py",
        "core/runtime/flow_runner.py",
        "core/runtime/flow_config.py",
        "core/runtime/dashboard_guard.py",
        "core/os/win/window.py",
        "core/os/win/mouse.py",
    ],

    # B) Фичи
    "B": [
        "core/features/__init__.py",
        "core/features/afterbuff_macros.py",
        "core/features/buff_after_respawn.py",
        "core/features/dashboard_reset.py",
        "core/features/flow_actions.py",
        "core/features/player_state.py",
        "core/features/post_tp_row.py",
        "core/features/restart_manager.py",
        "core/features/to_village.py",
        "core/features/tp_after_respawn.py",
    ],

    # C) Серверы
    "C": [
        "core/servers/__init__.py",
        "core/servers/base_config.py",
        "core/servers/registry.py",

        # l2mad
        "core/servers/l2mad/profile.py",
        "core/servers/l2mad/locations_map.py",
        "core/servers/l2mad/zones/*.py",
        "core/servers/l2mad/flows/*.py",
        "core/servers/l2mad/flows/rows/registry.py",
        "core/servers/l2mad/flows/rows/**/*.py",
        "core/servers/l2mad/templates/resolver.py",

        # boh
        "core/servers/boh/profile.py",
        "core/servers/boh/locations_map.py",
        "core/servers/boh/zones/*.py",
        "core/servers/boh/flows/*.py",
        "core/servers/boh/flows/rows/registry.py",
        "core/servers/boh/flows/rows/**/*.py",
        "core/servers/boh/templates/resolver.py",
    ],

    # D) Tk-UI
    "D": [
        "app/ui/__init__.py",
        "app/ui/account_settings.py",
        "app/ui/afterbuff_macros.py",
        "app/ui/buff_controls.py",
        "app/ui/interval_buff.py",
        "app/ui/respawn_controls.py",
        "app/ui/state_controls.py",
        "app/ui/tp_controls.py",
        "app/ui/updater_dialog.py",
        "app/ui/window_probe.py",
        "app/ui/widgets.py",
    ],

    # E) Обвязка/лаунчеры (новая структура launcher/)
    "E": [
        "app/__init__.py",
        "app/__main__.py",
        "app/launcher_bootstrap.py",

        "app/launcher/__init__.py",
        "app/launcher/base.py",
        "app/launcher/main.py",
        "app/launcher/wiring.py",
        "app/launcher/sections/*.py",

        "core/updater.py",
        "core/logging_setup.py",
    ],

    # F) Vision
    "F": [
        "core/vision/matching.py",
        "core/vision/utils/colors.py",
        "core/vision/win32/gdi_backend.py",
        "core/vision/capture/gdi.py",
        "core/vision/capture/window_bgr_capture.py",
        "core/vision/matching/template_matcher.py",
    ],

    # G) Arduino
    "G": [
        "core/arduino/safe_serial.py",
        "core/arduino/send_command.py",
        "core/arduino/send_safe.py",
        "core/arduino/serial_port.py",
    ],

    # H) Autofarm engine (server/*)
    "H": [
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

    # I) WebUI (HTML/CSS/JS) — без бинарных ассетов
    "I": [
        "app/webui/index.html",
        "app/webui/css/*.css",
        "app/webui/js/*.js",
        "app/webui/assets/*.txt",
    ],
}

OUT_FILENAMES = {
    "A": "A_core_io.txt",
    "B": "B_features.txt",
    "C": "C_servers.txt",
    "D": "D_ui_spec.txt",
    "E": "E_wrappers.txt",
    "F": "F_vision.txt",
    "G": "G_arduino.txt",
    "H": "H_autofarm.txt",
    "I": "I_webui.txt",
}

# ------------ СБОРЩИК ------------
def _iter_matches(root: Path, patterns: Iterable[str]) -> list[Path]:
    seen: set[Path] = set()
    out: list[Path] = []
    for pat in patterns:
        paths = sorted(root.glob(pat), key=lambda p: str(p).lower())
        if not paths and ("*" not in pat and "?" not in pat and "**" not in pat):
            out.append(root / f"__MISSING__::{pat}")
            continue
        for p in paths:
            if p.is_file() and _is_text_file(p):
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
        w.write(f"# === SECTION {letter} ===\n# root: {root}\n\n")
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
    ap = argparse.ArgumentParser(description="Собрать файлы по разделам в один текстовый дамп на раздел + единый манифест.")
    ap.add_argument("--root", default=".", help="корень проекта")
    ap.add_argument("--out", default="collected", help="каталог вывода")
    ap.add_argument("--sections", default="A,B,C,D,E,F,G,H,I", help="какие разделы собирать, через запятую")
    ap.add_argument("--manifest-name", default="manifest.txt", help="имя файла единого манифеста")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    out_dir = Path(args.out).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    all_entries: List[str] = []
    letters = [s.strip().upper() for s in args.sections.split(",") if s.strip()]
    for l in letters:
        if l not in SECTIONS:
            print(f"[skip] неизвестный раздел: {l}")
            continue
        inc, miss, entries = build_section(root, out_dir, l)
        print(f"[{l}] written -> {OUT_FILENAMES[l]}  files: {inc}  missing: {miss}")
        all_entries.extend(entries)

    # ЕДИНЫЙ МАНИФЕСТ
    manifest_path = out_dir / args.manifest-name if hasattr(args, "manifest-name") else out_dir / args.manifest_name
    # совместимость с argparse: использовать manifest_name
    manifest_path = out_dir / getattr(args, "manifest_name", "manifest.txt")
    with io.open(manifest_path, "w", encoding="utf-8", newline="\n") as mf:
        mf.write("# section\tstatus\tpath\n")
        for line in all_entries:
            mf.write(line + "\n")

    print(f"[done] output: {out_dir}")
    print(f"[manifest] {manifest_path.name}: {len(all_entries)} entries")

if __name__ == "__main__":
    sys.exit(main())
