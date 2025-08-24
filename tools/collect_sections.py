# tools/collect_sections.py
# usage: python tools/collect_sections.py --root . --out collected --sections A,B,C,D,E
from __future__ import annotations
import argparse, sys, os, io
from pathlib import Path
from typing import Iterable

# --- разделы и шаблоны ---
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
        "core/runtime/dashboard_guard.py",  # если есть
    ],
    # B) Фичи
    "B": [
        "core/features/tp_after_respawn.py",
        "core/features/to_village.py",
        "core/features/buff_after_respawn.py",
        "core/features/afterbuff_macros.py",
        "core/features/post_tp_row.py",
        "core/features/dashboard_reset.py",
    ],
    # C) Серверы: профили, карты, флоуы, зоны, rows
    "C": [
        "core/servers/registry.py",
        "core/servers/base_config.py",
        "core/servers/l2mad/profile.py",
        "core/servers/l2mad/locations_map.py",
        "core/servers/l2mad/templates/resolver.py",
        # TP flows (оба варианта)
        "core/servers/l2mad/flows/tp.py",
        "core/servers/l2mad/flows/tp_dashboard.py",
        "core/servers/l2mad/flows/tp_gatekeeper.py",
        # TP zones (оба варианта)
        "core/servers/l2mad/zones/tp.py",
        "core/servers/l2mad/zones/tp_dashboard.py",
        "core/servers/l2mad/zones/tp_gatekeeper.py",
        # Buff flows/zones
        "core/servers/l2mad/flows/buff*.py",
        "core/servers/l2mad/zones/buff.py",
        # Dashboard reset / restart
        "core/servers/l2mad/flows/dashboard_reset.py",
        "core/servers/l2mad/flows/restart.py",
        "core/servers/l2mad/zones/restart.py",
        "core/servers/l2mad/zones/state.py",
        # Rows registry + любые конкретные rows/*
        "core/servers/l2mad/flows/rows/registry.py",
        "core/servers/l2mad/flows/rows/**/*.py",
    ],
    # D) Tk-UI как спецификация поведения
    "D": [
        "app/ui/tp_controls.py",
        "app/ui/buff_controls.py",
        "app/ui/respawn_controls.py",
        "app/ui/state_controls.py",
        "app/ui/afterbuff_macros.py",
        "app/ui/window_probe.py",
        "app/ui/account_settings.py",
        "app/ui/updater_dialog.py",
        "app/ui/interval_buff.py",
        "app/ui/settings.py",
    ],
    # E) Контроллеры/обвязка
    "E": [
        "app/controllers/rows_controller.py",
        "app/launcher_bootstrap.py",
        "app/launcher_html.py",
    ],
    # F) Контроллеры/обвязка
    "F": [
      "core/vision/matching.py",
      "core/vision/utils/colors.py",
      "core/vision/win32/gdi_backend.py",
      "core/vision/capture/gdi.py",
      "core/vision/capture/window_bgr_capture.py",
      "core/vision/matching/template_matcher.py"
    ],
}

OUT_FILENAMES = {
    "A": "A_core_io.py",
    "B": "B_features.py",
    "C": "C_servers.py",
    "D": "D_ui_spec.py",
    "E": "E_wrappers.py",
    "F": "F_vision.py",
}

def _iter_matches(root: Path, patterns: Iterable[str]) -> list[Path]:
    seen: set[Path] = set()
    out: list[Path] = []
    for pat in patterns:
        # поддержка ** в C-разделе
        recursive = "**" in pat
        paths = sorted(root.glob(pat), key=lambda p: str(p).lower()) if recursive else sorted(root.glob(pat.replace("**/","")), key=lambda p: str(p).lower())
        if not paths and ("*" not in pat and "?" not in pat):
            # точный путь не найден — пометим «missing» пустой записью в манифесте
            out.append(root / f"__MISSING__::{pat}")
            continue
        for p in paths:
            if p.is_file() and p.suffix == ".py":
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

def build_section(root: Path, out_dir: Path, letter: str) -> tuple[int,int]:
    patterns = SECTIONS[letter]
    files = _iter_matches(root, patterns)

    dst = out_dir / OUT_FILENAMES[letter]
    dst.parent.mkdir(parents=True, exist_ok=True)

    included = 0
    missing = 0
    with io.open(dst, "w", encoding="utf-8", newline="\n") as w:
        w.write(f"# === SECTION {letter} ===\n# root: {root}\n\n")
        for p in files:
            if p.name.startswith("__MISSING__::"):
                missing += 1
                miss = str(p.name).split("::",1)[1]
                w.write(f"# --- MISSING: {miss}\n\n")
                continue
            rel = p.relative_to(root)
            w.write(f"# --- BEGIN FILE: {rel.as_posix()} ---\n")
            w.write(_read_text(p))
            if not str(_read_text(p)).endswith("\n"):
                w.write("\n")
            w.write(f"# --- END FILE: {rel.as_posix()} ---\n\n")
            included += 1

    # манифест
    (out_dir / f"{letter}.manifest.txt").write_text(
        "\n".join(
            [f"INCLUDE {p.relative_to(root).as_posix()}" for p in files if not p.name.startswith("__MISSING__::")]
            + [f"MISSING {str(p.name).split('::',1)[1]}" for p in files if p.name.startswith("__MISSING__::")]
        ),
        encoding="utf-8",
    )
    return included, missing

def main():
    ap = argparse.ArgumentParser(description="Собрать файлы по разделам A–E в один .py на раздел.")
    ap.add_argument("--root", default=".", help="корень проекта")
    ap.add_argument("--out", default="collected", help="каталог вывода")
    ap.add_argument("--sections", default="A,B,C,D,E,F", help="какие разделы собирать, через запятую")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    out_dir = Path(args.out).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    letters = [s.strip().upper() for s in args.sections.split(",") if s.strip()]
    for l in letters:
        if l not in SECTIONS:
            print(f"[skip] неизвестный раздел: {l}")
            continue
        inc, miss = build_section(root, out_dir, l)
        print(f"[{l}] written -> {OUT_FILENAMES[l]}  files: {inc}  missing: {miss}")

    print(f"[done] output: {out_dir}")

if __name__ == "__main__":
    sys.exit(main())
