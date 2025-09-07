# core/engines/player_state/tests/probe_hp_bar.py
from __future__ import annotations
import os
import sys
import time
from typing import Dict, Optional, Tuple, List

import numpy as np
import cv2

# --- bootstrap: allow running directly or as module ---
if __name__ == "__main__" and __package__ is None:
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "..")))

# GDI helpers
from core.vision.capture.gdi import find_window, get_window_info
from core.vision.capture.window_bgr_capture import capture_window_region_bgr
from core.vision.utils.colors import mask_for_colors_bgr

# ---------- НАСТРОЙКИ ----------
WINDOW_TITLES: List[str] = ["Lineage", "Lineage II", "L2MAD", "L2", "BOHPTS"]

# Зона STATE (клиентские координаты окна)
ZONE_STATE_LTRB: Tuple[int, int, int, int] = (0, 0, 165, 45)

# «Живые» цвета HP (RGB)
HP_ALIVE_RGB: List[Tuple[int, int, int]] = [
    (121, 28, 17)
]

# Допуск по цвету
COLOR_TOL: int = 1

# Период опроса
POLL_S: float = 1.0

# Имя файла эталона (в той же папке, что и скрипт)
TEMPLATE_NAME = "template.png"
# --------------------------------


def _find_game_window() -> Optional[Dict]:
    for t in WINDOW_TITLES:
        try:
            hwnd = find_window(t)
            if hwnd:
                info = get_window_info(hwnd, client=True) or {}
                try:
                    info["hwnd"] = int(hwnd)
                except Exception:
                    pass
                if all(k in info for k in ("x", "y", "width", "height")):
                    return info
        except Exception:
            pass
    return None


def _load_baseline(template_path: str) -> int:
    """
    Считываем template.png (BGR), строим маску по HP_ALIVE_RGB и считаем пиксели.
    Это число принимаем за 100% HP.
    """
    img = cv2.imread(template_path, cv2.IMREAD_COLOR)
    if img is None or img.size == 0:
        raise RuntimeError(f"Не удалось загрузить шаблон: {template_path}")
    mask = mask_for_colors_bgr(img, HP_ALIVE_RGB, tol=COLOR_TOL)
    return int(np.count_nonzero(mask))


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    template_path = os.path.join(here, TEMPLATE_NAME)
    try:
        baseline_px = _load_baseline(template_path)
    except Exception as e:
        print(f"[hp_color] Ошибка инициализации: {e}")
        return

    if baseline_px <= 0:
        print("[hp_color] На эталоне не найдено ни одного пикселя целевых цветов (baseline=0). Завершение.")
        return

    print(f"[hp_color] baseline(template)={baseline_px} px | colors={len(HP_ALIVE_RGB)} tol={COLOR_TOL} | zone={ZONE_STATE_LTRB}")

    win = None

    try:
        while True:
            if not win:
                win = _find_game_window()
                if not win:
                    print("[hp_color] Окно не найдено. Повтор через 1.5с…")
                    time.sleep(1.5)
                    continue
                print(f"[hp_color] Окно найдено: {win.get('width')}x{win.get('height')}")

            img = capture_window_region_bgr(win, ZONE_STATE_LTRB)
            if img is None or img.size == 0:
                print("[hp_color] Кадр пуст. Повтор…")
                time.sleep(POLL_S)
                continue

            mask = mask_for_colors_bgr(img, HP_ALIVE_RGB, tol=COLOR_TOL)
            alive_px = int(np.count_nonzero(mask))

            hp_pct = int(round(min(1.0, alive_px / baseline_px) * 100.0))

            print(f"[hp_color] alive_px={alive_px} / baseline={baseline_px} → hp≈{hp_pct:3d}%")

            time.sleep(POLL_S)
    except KeyboardInterrupt:
        print("\n[hp_color] Завершено пользователем")


if __name__ == "__main__":
    main()
