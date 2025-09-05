# core/engines/player_state/server/boh/engine.py
from __future__ import annotations
import time
from typing import Dict, Any, Optional, Callable, Tuple, List

import numpy as np
from core.vision.capture.window_bgr_capture import capture_window_region_bgr
from core.vision.utils.colors import mask_for_colors_bgr, biggest_horizontal_band

from .state_data import (
    ZONES,
    COLORS,
    HP_TOLERANCE_ALIVE,
    HP_TOLERANCE_DEAD,
    DEFAULT_POLL_INTERVAL,
)

class PlayerState:
    __slots__ = ("hp_ratio", "ts")
    def __init__(self, hp_ratio: float = 1.0, ts: float = 0.0):
        self.hp_ratio = float(hp_ratio)
        self.ts = float(ts)

def _emit(status_cb: Optional[Callable[[str, Optional[bool]], None]], msg: str, ok: Optional[bool] = None):
    try:
        if callable(status_cb):
            status_cb(msg, ok)
        else:
            print(f"[player_state/boh] {msg}")
    except Exception:
        print(f"[player_state/boh] {msg}")

def _compute_hp_ratio(
    win: Dict,
    zone_ltrb: Tuple[int, int, int, int],
    colors_alive: List[Tuple[int, int, int]],
    colors_dead: List[Tuple[int, int, int]],
    tol_alive: int,
    tol_dead: int,
    prev_ratio: float,
) -> float:
    img = capture_window_region_bgr(win, zone_ltrb)
    if img is None or img.size == 0:
        return prev_ratio

    alive_mask = mask_for_colors_bgr(img, colors_alive, tol=tol_alive) if colors_alive else None
    dead_mask  = mask_for_colors_bgr(img, colors_dead,  tol=tol_dead)  if colors_dead  else None

    if alive_mask is not None and dead_mask is not None:
        a_rect = biggest_horizontal_band(alive_mask)
        d_rect = biggest_horizontal_band(dead_mask)
        a_w = a_rect[2] if a_rect else 0
        d_w = d_rect[2] if d_rect else 0
        total = a_w + d_w
        if total <= 0:
            a_area = int(np.count_nonzero(alive_mask))
            d_area = int(np.count_nonzero(dead_mask))
            total = a_area + d_area
            return (a_area / total) if total > 0 else prev_ratio
        return a_w / total

    if alive_mask is not None:
        a_area = int(np.count_nonzero(alive_mask))
        total = img.shape[0] * img.shape[1]
        return (a_area / total) if total > 0 else prev_ratio

    if dead_mask is not None:
        d_area = int(np.count_nonzero(dead_mask))
        total = img.shape[0] * img.shape[1]
        return 1.0 - ((d_area / total) if total > 0 else 0.0)

    return prev_ratio

def start(ctx_base: Dict[str, Any], cfg: Dict[str, Any]) -> bool:
    get_window = ctx_base["get_window"]
    on_status: Callable[[str, Optional[bool]], None] = ctx_base.get("on_status") or (lambda *_: None)
    on_update: Optional[Callable[[Dict[str, Any]], None]] = ctx_base.get("on_update")
    should_abort: Callable[[], bool] = ctx_base.get("should_abort") or (lambda: False)

    zone = ZONES.get("state")
    if not zone:
        _emit(on_status, "[boh] зона STATE не задана", False)
        return False

    colors_alive = COLORS.get("hp_alive_rgb", []) or []
    colors_dead = COLORS.get("hp_dead_rgb", []) or []

    tol_alive = int(cfg.get("hp_tol_alive", HP_TOLERANCE_ALIVE))
    tol_dead  = int(cfg.get("hp_tol_dead",  HP_TOLERANCE_DEAD))
    poll_interval = float(cfg.get("poll_interval", DEFAULT_POLL_INTERVAL))

    prev_ratio = 1.0
    _emit(on_status, f"[boh] player_state старт (poll={poll_interval}s, tol_alive={tol_alive}, tol_dead={tol_dead})…", None)

    try:
        while True:
            if should_abort():
                _emit(on_status, "[boh] остановлено пользователем", True)
                return True

            try:
                win = get_window() or {}
            except Exception:
                win = {}

            if not win:
                time.sleep(poll_interval)
                continue

            hp_ratio = _compute_hp_ratio(win, zone, colors_alive, colors_dead, tol_alive, tol_dead, prev_ratio)
            prev_ratio = hp_ratio

            if on_update:
                try:
                    on_update({"hp_ratio": float(hp_ratio), "ts": time.time()})
                except Exception:
                    pass

            time.sleep(poll_interval)
    except Exception as e:
        _emit(on_status, f"[boh] ошибка: {e}", False)
        return False
