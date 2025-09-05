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
    """
    %HP = alive_px / (alive_px + dead_px_adj),
    где dead_px_adj = max(0, dead_px - DEAD_BASELINE_PX).
    Перекрытия (alive & dead) из числителя исключаем.
    """
    # базовая «наводка» мёртвых пикселей при полном HP
    DEAD_BASELINE_PX = 4

    img = capture_window_region_bgr(win, zone_ltrb)
    if img is None or img.size == 0:
        return prev_ratio

    alive_mask = mask_for_colors_bgr(img, colors_alive, tol=tol_alive) if colors_alive else None
    dead_mask  = mask_for_colors_bgr(img, colors_dead,  tol=tol_dead)  if colors_dead  else None

    h, w = img.shape[:2]
    total_pixels = int(h * w) if h and w else 0

    if alive_mask is not None and dead_mask is not None:
        alive_bin = (alive_mask > 0)
        dead_bin  = (dead_mask  > 0)

        alive_only = int(np.count_nonzero(alive_bin & ~dead_bin))
        dead_only  = int(np.count_nonzero(dead_bin  & ~alive_bin))

        dead_only_adj = max(0, dead_only - DEAD_BASELINE_PX)
        denom = alive_only + dead_only_adj
        if denom > 0:
            return float(alive_only) / float(denom)
        return prev_ratio

    if alive_mask is not None and total_pixels > 0:
        alive_px = int(np.count_nonzero(alive_mask))
        return float(alive_px) / float(total_pixels)

    if dead_mask is not None and total_pixels > 0:
        dead_px = int(np.count_nonzero(dead_mask))
        dead_adj = max(0, dead_px - DEAD_BASELINE_PX)
        return 1.0 - (float(dead_adj) / float(total_pixels))

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

            # DEBUG: считаем количество пикселей dead|alive_colors и логируем
            try:
                dbg_img = capture_window_region_bgr(win, zone)
                if dbg_img is not None and dbg_img.size:
                    dead_mask_dbg = mask_for_colors_bgr(dbg_img, colors_dead, tol=tol_dead) if colors_dead else None
                    alive_mask_dbg = mask_for_colors_bgr(dbg_img, colors_alive, tol=tol_alive) if colors_alive else None
                    if dead_mask_dbg is not None:
                        dead_px = int(np.count_nonzero(dead_mask_dbg))
                        _emit(on_status, f"[HP] dead_pixels={dead_px}", None)
                    if alive_mask_dbg is not None:
                        alive_px = int(np.count_nonzero(alive_mask_dbg))
                        _emit(on_status, f"[HP] alive_pixels={alive_px}", None)
            except Exception:
                pass

            if on_update:
                try:
                    on_update({"hp_ratio": float(hp_ratio), "ts": time.time()})
                except Exception:
                    pass

            time.sleep(poll_interval)
    except Exception as e:
        _emit(on_status, f"[boh] ошибка: {e}", False)
        return False
