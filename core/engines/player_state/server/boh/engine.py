# core/engines/player_state/server/boh/engine.py
from __future__ import annotations
import time
from typing import Dict, Any, Optional, Callable, Tuple, List

import numpy as np
import cv2

from core.vision.capture.window_bgr_capture import capture_window_region_bgr

# === Параметры по умолчанию для метода «полоса по целевому цвету» ===
# Один «эталонный» цвет HP (RGB)
DEFAULT_HP_PROBE_RGB: Tuple[int, int, int] = (135, 30, 22)
# Допуск по цвету
DEFAULT_HP_COLOR_TOL: int = 5
# Длина «полной» полосы (в пикселях) — соответствует 100% HP
DEFAULT_HP_FULL_PX: int = 74
# Геометрия зоны поиска: ширина x высота.
# БЫЛО: нижняя граница зоны совпадала с центром экрана.
# СТАЛО: нижняя граница смещена ВНИЗ на extra_down пикселей от центра экрана.
DEFAULT_ZONE_W: int = 120
DEFAULT_ZONE_H: int = 250
DEFAULT_ZONE_EXTRA_DOWN: int = 100  # ← добавлено: расширяем вниз от центра
# Период опроса по умолчанию (сек)
DEFAULT_POLL_INTERVAL: float = 0.25


class PlayerState:
    __slots__ = ("hp_ratio", "ts")
    def __init__(self, hp_ratio: float = 1.0, ts: float = 0.0):
        self.hp_ratio = float(hp_ratio)
        self.ts = float(ts)


def _emit(status_cb: Optional[Callable[[str, Optional[bool]], None]], msg: str, ok: Optional[bool] = None):
    # В проде стараемся не спамить лог; функция остаётся для ошибок/старт-стоп сообщений.
    try:
        if callable(status_cb):
            status_cb(msg, ok)
        else:
            print(f"[player_state/boh] {msg}")
    except Exception:
        print(f"[player_state/boh] {msg}")


def _compute_center_bottom_zone_ltrb(
    win: Dict, w: int, h: int, extra_down: int = DEFAULT_ZONE_EXTRA_DOWN
) -> Tuple[int, int, int, int]:
    """
    Возвращает (l, t, r, b) в клиентских координатах окна.

    Геометрия «РАСШИРИТЬ вниз»:
      - по X остаёмся по центру;
      - верх зоны как раньше (centerY - h);
      - нижнюю границу опускаем на extra_down (centerY + extra_down), не выходя за низ окна;
      - в итоге фактическая высота = h + extra_down (с учётом клипа по нижней границе).
    """
    ww, wh = int(win.get("width", 0)), int(win.get("height", 0))
    cx, cy = ww // 2, wh // 2

    # По X центрируем и аккуратно клипуем
    l = max(0, min(cx - w // 2, ww - w))
    r = min(ww, l + w)

    # Верх — как было раньше (нижняя граница на centerY)
    t0 = cy - h
    # Низ — расширяем вниз от центра
    b = min(wh, cy + int(extra_down))

    # Клип верха в допустимые координаты
    t = max(0, min(t0, wh))

    # Гарантия непустой зоны
    if t >= b:
        t = max(0, b - 1)

    return (l, t, r, b)


def _mask_for_color_bgr(img_bgr, color_rgb: Tuple[int, int, int], tol: int) -> np.ndarray:
    """
    Построить бинарную маску по одному RGB-цвету с допуском.
    Вход img_bgr — OpenCV BGR.
    """
    r, g, b = color_rgb
    lower = np.array([b - tol, g - tol, r - tol], dtype=np.int16)
    upper = np.array([b + tol, g + tol, r + tol], dtype=np.int16)
    lower = np.clip(lower, 0, 255).astype(np.uint8)
    upper = np.clip(upper, 0, 255).astype(np.uint8)
    return cv2.inRange(img_bgr, lower, upper)


def _longest_horizontal_run(mask_bin: np.ndarray) -> int:
    """
    Максимальная длина подряд идущих положительных пикселей в любой строке маски.
    """
    if mask_bin is None or mask_bin.size == 0:
        return 0

    m = (mask_bin > 0)
    h, _ = m.shape[:2]
    best_len = 0

    for y in range(h):
        row = m[y]
        if not row.any():
            continue
        r = row.astype(np.int8)
        edges = np.diff(np.concatenate(([0], r, [0])))
        starts = np.where(edges == 1)[0]
        ends = np.where(edges == -1)[0]
        if starts.size and ends.size:
            lengths = ends - starts
            mx = int(lengths.max(initial=0))
            if mx > best_len:
                best_len = mx

    return best_len


def _estimate_hp_ratio_from_colorbar(
    win: Dict,
    probe_color_rgb: Tuple[int, int, int],
    color_tol: int,
    zone_w: int,
    zone_h: int,
    full_px: int,
    prev_ratio: float,
    *,
    zone_extra_down: int = DEFAULT_ZONE_EXTRA_DOWN,
) -> float:
    """
    1) Захватываем динамическую зону:
       - центр по X — центр экрана,
       - нижняя граница на (центр_экрана_Y + zone_extra_down).
    2) Строим маску по целевому цвету с допуском, слегка склеиваем горизонтально.
    3) Берём максимальный горизонтальный пробег единиц и нормируем к full_px.
    """
    if not win or zone_w <= 0 or zone_h <= 0 or full_px <= 0:
        return prev_ratio

    ltrb = _compute_center_bottom_zone_ltrb(win, zone_w, zone_h, zone_extra_down)
    img = capture_window_region_bgr(win, ltrb)
    if img is None or img.size == 0:
        return prev_ratio

    raw = _mask_for_color_bgr(img, probe_color_rgb, color_tol)
    # Слегка «склеиваем» разрывы по горизонтали
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 1))
    merged = cv2.morphologyEx(raw, cv2.MORPH_CLOSE, kernel, iterations=1)

    max_run = _longest_horizontal_run(merged)
    ratio = max(0.0, min(1.0, float(max_run) / float(full_px)))
    return ratio


def start(ctx_base: Dict[str, Any], cfg: Dict[str, Any]) -> bool:
    """
    Движок состояния игрока (HP) для BOH:
    вычисляет hp_ratio по длине цветной полосы (шаблонный цвет) в окне клиента.
    """
    get_window = ctx_base["get_window"]
    on_status: Callable[[str, Optional[bool]], None] = ctx_base.get("on_status") or (lambda *_: None)
    on_update: Optional[Callable[[Dict[str, Any]], None]] = ctx_base.get("on_update")
    should_abort: Callable[[], bool] = ctx_base.get("should_abort") or (lambda: False)

    # Конфиг с дефолтами (поддержка переопределений из cfg)
    probe_color_rgb: Tuple[int, int, int] = tuple(cfg.get("hp_probe_color_rgb", DEFAULT_HP_PROBE_RGB))  # type: ignore
    color_tol: int = int(cfg.get("hp_color_tol", DEFAULT_HP_COLOR_TOL))
    zone_w: int = int(cfg.get("hp_zone_w", DEFAULT_ZONE_W))
    zone_h: int = int(cfg.get("hp_zone_h", DEFAULT_ZONE_H))
    zone_extra_down: int = int(cfg.get("hp_zone_extra_down", DEFAULT_ZONE_EXTRA_DOWN))  # ← новое
    full_px: int = int(cfg.get("hp_full_px", DEFAULT_HP_FULL_PX))
    poll_interval: float = float(cfg.get("poll_interval", DEFAULT_POLL_INTERVAL))

    prev_ratio = 1.0
    _emit(on_status, f"[boh] player_state старт (poll={poll_interval}s, extra_down={zone_extra_down})", None)

    try:
        while True:
            if should_abort():
                return True

            try:
                win = get_window() or {}
            except Exception:
                win = {}

            if not win:
                time.sleep(poll_interval)
                continue

            try:
                hp_ratio = _estimate_hp_ratio_from_colorbar(
                    win=win,
                    probe_color_rgb=probe_color_rgb,
                    color_tol=color_tol,
                    zone_w=zone_w,
                    zone_h=zone_h,
                    full_px=full_px,
                    prev_ratio=prev_ratio,
                    zone_extra_down=zone_extra_down,
                )
                prev_ratio = hp_ratio
            except Exception:
                # сохраняем предыдущий, чтобы не дёргать UI
                hp_ratio = prev_ratio

            if on_update:
                try:
                    on_update({"hp_ratio": float(hp_ratio), "ts": time.time()})
                except Exception:
                    pass

            time.sleep(poll_interval)
    except Exception as e:
        _emit(on_status, f"[boh] ошибка: {e}", False)
        return False
