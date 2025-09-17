from __future__ import annotations
import time
from typing import Dict, Any, Optional, Callable, Tuple, List

import numpy as np
import cv2

from core.vision.capture.window_bgr_capture import capture_window_region_bgr
from core.logging import console

# === Параметры по умолчанию для метода «полоса по целевому цвету» ===
DEFAULT_HP_PROBE_RGB: Tuple[int, int, int] = (135, 30, 22)
DEFAULT_HP_COLOR_TOL: int = 5
DEFAULT_HP_FULL_PX: int = 74
DEFAULT_ZONE_W: int = 120
DEFAULT_ZONE_H: int = 250
DEFAULT_ZONE_EXTRA_DOWN: int = 100
DEFAULT_POLL_INTERVAL: float = 0.25

# --- Данные фолбэка (BOH) ---
from .state_data import (
    ZONES as _SD_ZONES,
    COLORS as _SD_COLORS,
    HP_TOLERANCE_ALIVE as _SD_HP_TOL_ALIVE,
    DEFAULT_POLL_INTERVAL as _SD_FB_POLL_INTERVAL,
)


class PlayerState:
    __slots__ = ("hp_ratio", "ts")
    def __init__(self, hp_ratio: float = 1.0, ts: float = 0.0):
        self.hp_ratio = float(hp_ratio)
        self.ts = float(ts)


def _compute_center_bottom_zone_ltrb(
    win: Dict, w: int, h: int, extra_down: int = DEFAULT_ZONE_EXTRA_DOWN
) -> Tuple[int, int, int, int]:
    ww, wh = int(win.get("width", 0)), int(win.get("height", 0))
    cx, cy = ww // 2, wh // 2

    l = max(0, min(cx - w // 2, ww - w))
    r = min(ww, l + w)

    t0 = cy - h
    b = min(wh, cy + int(extra_down))
    t = max(0, min(t0, wh))
    if t >= b:
        t = max(0, b - 1)

    return (l, t, r, b)


def _mask_for_color_bgr(img_bgr, color_rgb: Tuple[int, int, int], tol: int) -> np.ndarray:
    r, g, b = color_rgb
    lower = np.array([b - tol, g - tol, r - tol], dtype=np.int16)
    upper = np.array([b + tol, g + tol, r + tol], dtype=np.int16)
    lower = np.clip(lower, 0, 255).astype(np.uint8)
    upper = np.clip(upper, 0, 255).astype(np.uint8)
    return cv2.inRange(img_bgr, lower, upper)


def _mask_for_colors_bgr(img_bgr, colors_rgb: List[Tuple[int, int, int]], tol: int) -> np.ndarray:
    if img_bgr is None or img_bgr.size == 0:
        return np.zeros((0, 0), dtype=np.uint8)
    acc = None
    for rgb in colors_rgb or []:
        m = _mask_for_color_bgr(img_bgr, rgb, tol)
        acc = m if acc is None else cv2.bitwise_or(acc, m)
    if acc is None:
        acc = np.zeros(img_bgr.shape[:2], dtype=np.uint8)
    return acc


def _longest_horizontal_run(mask_bin: np.ndarray) -> int:
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
    if not win or zone_w <= 0 or zone_h <= 0 or full_px <= 0:
        return prev_ratio

    ltrb = _compute_center_bottom_zone_ltrb(win, zone_w, zone_h, zone_extra_down)
    img = capture_window_region_bgr(win, ltrb)
    if img is None or img.size == 0:
        return prev_ratio

    raw = _mask_for_color_bgr(img, probe_color_rgb, color_tol)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 1))
    merged = cv2.morphologyEx(raw, cv2.MORPH_CLOSE, kernel, iterations=1)

    max_run = _longest_horizontal_run(merged)
    ratio = max(0.0, min(1.0, float(max_run) / float(full_px)))
    return ratio


# ─────────────────────────────────────────────────────────────────────────────
#   HP Fallback (BOH only; console.log; + "жив" эвристика 1.5с при мигании)
# ─────────────────────────────────────────────────────────────────────────────
class _HPFallbackTracker:
    def __init__(self):
        self.learned: bool = False
        self.bar_rect: Optional[Tuple[int, int, int, int]] = None  # LTRB в координатах окна
        self.bar_len: int = 0  # число колонок (r-l)
        self.active: bool = False
        self._last_log_ts: float = 0.0
        self.last_alive_seen_ts: float = 0.0  # когда в последний раз видели «живые» цвета (по колонкам)

    # обучение на первом точном 100%: левый/правый край по всей зоне state
    def learn(self, win: Dict) -> None:
        if self.learned:
            return
        try:
            st = _SD_ZONES["state"]
            state_l = int(st.get("left", 0))
            state_t = int(st.get("top", 0))
            state_w = int(st.get("width", 0))
            state_h = int(st.get("height", 0))
            state_r = state_l + max(0, state_w)
            state_b = state_t + max(0, state_h)
        except Exception:
            return
        ltrb_state = (state_l, state_t, state_r, state_b)
        img = capture_window_region_bgr(win, ltrb_state)
        if img is None or img.size == 0:
            return

        alive_colors = list(_SD_COLORS.get("hp_alive_rgb_fallback", []) or [])
        tol = int(_SD_HP_TOL_ALIVE)
        mask = _mask_for_colors_bgr(img, alive_colors, tol)
        if mask.size == 0:
            return

        col_any = (mask > 0).any(axis=0)
        xs = np.where(col_any)[0]
        if xs.size == 0:
            return

        x0 = int(xs.min())
        x1 = int(xs.max())
        total = int(x1 - x0 + 1)
        if total <= 0:
            return

        seg = mask[:, x0:x1 + 1]
        rows_any = (seg > 0).any(axis=1)
        if rows_any.any():
            y0 = int(np.argmax(rows_any))
            y1 = int(len(rows_any) - 1 - np.argmax(rows_any[::-1]))
        else:
            y0, y1 = 0, img.shape[0] - 1

        l = int(state_l + x0)
        r = int(state_l + x1 + 1)  # right-exclusive
        t = int(state_t + y0)
        b = int(state_t + y1 + 1)  # bottom-exclusive
        self.bar_rect = (l, t, r, b)
        self.bar_len = total
        self.learned = True

    # мгновенный замер фолбэка (без троттлинга)
    def probe_now(self, win: Dict) -> Optional[float]:
        if not (self.learned and self.bar_rect and self.bar_len > 0):
            return None
        l, t, r, b = self.bar_rect
        img = capture_window_region_bgr(win, (l, t, r, b))
        if img is None or img.size == 0:
            return None

        alive_colors = list(_SD_COLORS.get("hp_alive_rgb_fallback", []) or [])
        tol = int(_SD_HP_TOL_ALIVE)
        mask = _mask_for_colors_bgr(img, alive_colors, tol)
        if mask.size == 0:
            return None

        col_any = (mask > 0).any(axis=0)
        total = int(col_any.size)
        if total <= 0:
            return None
        alive = int(col_any.sum())
        ratio = max(0.0, min(1.0, float(alive) / float(total)))

        # фиксируем факт «живых» цветов для 1.5с-эвристики
        if alive > 0:
            self.last_alive_seen_ts = time.time()

        return ratio

    # периодический лог (раз в 1с)
    def maybe_log(self, win: Dict, now: float) -> None:
        if not self.active:
            return
        if now - self._last_log_ts < float(_SD_FB_POLL_INTERVAL):
            return
        val = self.probe_now(win)
        if val is None:
            return
        l, t, r, b = self.bar_rect or (0, 0, 0, 0)
        total = max(1, r - l)
        alive = int(round(val * total))
        console.log(f"[player_state/boh/fallback] hp≈{int(val*100)}% ({alive}/{total}), rect=({l},{t},{r},{b})")
        self._last_log_ts = now


def start(ctx_base: Dict[str, Any], cfg: Dict[str, Any]) -> bool:
    """
    BOH HP-движок с фолбэком:
    - основной замер по полосе;
    - фолбэк после обучения (первый hp==1.0): при основном hp<0.01 считаем колонками «живые» цвета;
    - если фолбэк ≥0.01 → фолбэк активен (лог 1c; основной не публикует on_update);
      если фолбэк <0.01 → ноль подтверждён, фолбэк не включаем;
    - эвристика «жив» при мигающем HP: если в течение 1.5с видели «живые» цвета, шлём наверх
      сигнал fallback_alive (пул: alive=True, hp скрыт, HUD предупреждение).
    """
    get_window = ctx_base["get_window"]
    on_update: Optional[Callable[[Dict[str, Any]], None]] = ctx_base.get("on_update")
    should_abort: Callable[[], bool] = ctx_base.get("should_abort") or (lambda: False)
    is_paused: Callable[[], bool] = ctx_base.get("is_paused") or (lambda: False)

    probe_color_rgb: Tuple[int, int, int] = tuple(cfg.get("hp_probe_color_rgb", DEFAULT_HP_PROBE_RGB))  # type: ignore
    color_tol: int = int(cfg.get("hp_color_tol", DEFAULT_HP_COLOR_TOL))
    zone_w: int = int(cfg.get("hp_zone_w", DEFAULT_ZONE_W))
    zone_h: int = int(cfg.get("hp_zone_h", DEFAULT_ZONE_H))
    zone_extra_down: int = int(cfg.get("hp_zone_extra_down", DEFAULT_ZONE_EXTRA_DOWN))
    full_px: int = int(cfg.get("hp_full_px", DEFAULT_HP_FULL_PX))
    poll_interval: float = float(cfg.get("poll_interval", DEFAULT_POLL_INTERVAL))

    tracker = _HPFallbackTracker()

    prev_ratio = 1.0
    was_paused = False
    console.log(f"[player_state/boh] start (poll={poll_interval}s, extra_down={zone_extra_down})")

    try:
        while True:
            if should_abort():
                return True

            # пауза
            if is_paused():
                if not was_paused:
                    was_paused = True
                    if on_update:
                        try:
                            on_update({"paused": True, "hp_ratio": None, "cp_ratio": None, "ts": time.time()})
                        except Exception:
                            pass
                time.sleep(poll_interval)
                continue
            else:
                if was_paused:
                    was_paused = False

            # окно
            try:
                win = get_window() or {}
            except Exception:
                win = {}

            if not win:
                time.sleep(poll_interval)
                continue

            # основной замер
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
                hp_ratio = prev_ratio

            now = time.time()

            # обучение на первом точном 100%
            if (not tracker.learned) and (hp_ratio == 1.0):
                tracker.learn(win)

            # если основной <0.01 — опросить фолбэк СЕЙЧАС
            fb_val: Optional[float] = None
            if tracker.learned and hp_ratio < 0.01:
                fb_val = tracker.probe_now(win)
                # включение/выключение режима фолбэка для логов
                if fb_val is not None and fb_val >= 0.01:
                    tracker.active = True
                elif fb_val is not None and fb_val < 0.01:
                    tracker.active = False

                # эвристика «жив» при мигании HP (1.5с с момента последнего «живого» столбца)
                if (now - tracker.last_alive_seen_ts) <= 1.5:
                    if on_update:
                        try:
                            on_update({"fallback_alive": True, "ts": now})
                        except Exception:
                            pass
                    # не публикуем основной hp в этот тик
                    time.sleep(poll_interval)
                    continue

            # деактивация фолбэка при основном >0.01
            handover_to_main = False
            if tracker.active and hp_ratio > 0.01:
                tracker.active = False
                handover_to_main = True  # вернуть задачу основному движку

            # вывод
            if tracker.active:
                tracker.maybe_log(win, now)  # только лог раз в 1с
            else:
                if on_update:
                    try:
                        payload = {"hp_ratio": float(hp_ratio), "ts": now}
                        if handover_to_main:
                            payload["fallback_clear_hud"] = True
                        on_update(payload)
                    except Exception:
                        pass

            time.sleep(poll_interval)
    except Exception as e:
        console.log(f"[player_state/boh] error: {e}")
        return False
