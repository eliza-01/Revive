# core/engines/player_state/tests/probe_hp_templates.py
from __future__ import annotations
import os
import sys
import time
from typing import Dict, Optional, Tuple

import numpy as np
import cv2

# --- bootstrap so the script can be run directly or as a module ---
if __name__ == "__main__" and __package__ is None:
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "..")))

# GDI helpers (поиск окна и инфо о клиентской области)
from core.vision.capture.gdi import find_window, get_window_info
from core.vision.capture.window_bgr_capture import capture_window_region_bgr
from core.vision.utils.colors import mask_for_colors_bgr

# ------ ПАРАМЕТРЫ ТЕСТА ------
WINDOW_TITLES = ["Lineage", "Lineage II", "L2MAD", "L2", "BOHPTS"]

# Целевой цвет (RGB), заданный пользователем
TARGET_RGB: Tuple[int, int, int] = (135, 30, 22)
# Допуск по цвету (0..255) — при необходимости подстрой
COLOR_TOL = 5

# Нормировка: 74 пикселя соответствуют 100% HP
HP_FULL_PX = 74

# Геометрия зоны:
# ширина x высота = 120x250, при этом ЦЕНТР НИЖНЕЙ ГРАНИЦЫ зоны совпадает с центром экрана (клиентской области окна)
ZONE_W, ZONE_H = 120, 250

# Период логирования/обновления (сек)
POLL_S = 0.7
# --------------------------------


def _find_game_window() -> Optional[Dict]:
    """Находим окно по одному из известных заголовков."""
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


def _compute_zone_ltrb(win: Dict) -> Tuple[int, int, int, int]:
    """
    Вычисляем (l, t, r, b) в КЛИЕНТСКИХ координатах:
    центр нижней границы зоны совпадает с центром окна.
    """
    ww, wh = int(win["width"]), int(win["height"])
    cx, cy = ww // 2, wh // 2  # центр экрана

    half_w = ZONE_W // 2
    l = cx - half_w
    r = cx + (ZONE_W - half_w)  # чтобы точно получить ширину 120 при нечетных знач.
    b = cy
    t = b - ZONE_H

    # Клайп по клиентской области на всякий случай
    l = max(0, l)
    t = max(0, t)
    r = min(ww, r)
    b = min(wh, b)
    return (l, t, r, b)


def _longest_horizontal_run(mask_bin: np.ndarray) -> Tuple[int, int]:
    """
    Возвращает (max_run_len, y_row), где max_run_len — максимальная длина
    подряд идущих положительных пикселей (True/255) по любой строке.
    y_row — индекс строки, где найден максимум, либо -1 если пусто.
    """
    if mask_bin is None or mask_bin.size == 0:
        return 0, -1

    # Приведем к булевому виду
    m = (mask_bin > 0)
    h, w = m.shape[:2]
    best_len, best_y = 0, -1

    for y in range(h):
        row = m[y]
        if not row.any():
            continue
        # Поиск длин пробега True
        r = row.astype(np.int8)
        edges = np.diff(np.concatenate(([0], r, [0])))
        starts = np.where(edges == 1)[0]
        ends = np.where(edges == -1)[0]
        if starts.size and ends.size:
            lengths = ends - starts
            mx = int(lengths.max(initial=0))
            if mx > best_len:
                best_len, best_y = mx, y

    return best_len, best_y


def _prepare_mask(img_bgr: np.ndarray) -> np.ndarray:
    """
    Создаем бинарную маску по целевому цвету с допуском.
    Для устойчивости слегка «склеиваем» разрывы горизонтально.
    """
    raw = mask_for_colors_bgr(img_bgr, [TARGET_RGB], tol=COLOR_TOL)
    # Небольшая горизонтальная морфология для склеивания дырок
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 1))
    merged = cv2.morphologyEx(raw, cv2.MORPH_CLOSE, kernel, iterations=1)
    return merged


def main():
    print(f"[hp_probe] target RGB={TARGET_RGB} tol={COLOR_TOL} | HP_FULL_PX={HP_FULL_PX} | zone={ZONE_W}x{ZONE_H}")
    win = None

    # Печатаем разово подсказку по управлению
    print("[hp_probe] Поиск окна игры… (допустимые заголовки:", ", ".join(WINDOW_TITLES), ")")

    last_zone = None

    try:
        while True:
            if not win:
                win = _find_game_window()
                if not win:
                    print("[hp_probe] Окно не найдено. Оставьте клиент открытым/несвернутым. Повтор через 1.5с…")
                    time.sleep(1.5)
                    continue
                # как только нашли — сообщим зону
                ltrb = _compute_zone_ltrb(win)
                last_zone = ltrb
                print(f"[hp_probe] Окно найдено. Клиент={win['width']}x{win['height']}. Зона LTRB={ltrb}")

            # Захват зоны
            try:
                ltrb = _compute_zone_ltrb(win)
                if ltrb != last_zone:
                    print(f"[hp_probe] Зона LTRB обновлена: {ltrb}")
                    last_zone = ltrb
                img = capture_window_region_bgr(win, ltrb)
            except Exception as e:
                print(f"[hp_probe] Ошибка захвата: {e}")
                img = None

            if img is None or img.size == 0:
                print("[hp_probe] Кадр пуст. Повтор…")
                time.sleep(POLL_S)
                continue

            # Маска по цвету и оценка длины полосы
            mask = _prepare_mask(img)
            max_run, row_y = _longest_horizontal_run(mask)

            # Нормировка в %
            pct = int(round(min(max_run, HP_FULL_PX) * 100.0 / HP_FULL_PX)) if HP_FULL_PX > 0 else 0

            # Отладочные счетчики
            total_match = int(np.count_nonzero(mask))
            h, w = mask.shape[:2]

            # ЛОГ
            print(
                f"[hp_probe] run={max_run:3d}px (row={row_y:3d}) "
                f"→ HP≈{pct:3d}%   | matches={total_match:5d} / zone={w}x{h}"
            )

            time.sleep(POLL_S)
    except KeyboardInterrupt:
        print("\n[hp_probe] Завершено пользователем")


if __name__ == "__main__":
    main()
