# _archive/core/features/archive/player_state.py
# Подсчёт HP по цветам в общей зоне STATE. Без OCR.
import importlib
import threading
import time
from typing import Callable, Optional, Dict

import numpy as np
from core.vision.utils.colors import mask_for_colors_bgr, biggest_horizontal_band
from core.vision.capture.window_bgr_capture import capture_window_region_bgr

class PlayerState:
    __slots__ = ("hp_ratio", "cp_ratio", "ts")
    def __init__(self, hp_ratio: float = 1.0, cp_ratio: float = 1.0, ts: float = 0.0):
        self.hp_ratio = hp_ratio
        self.cp_ratio = cp_ratio
        self.ts = ts

# --- unified alive check ---
def is_alive(state: "PlayerState", zero_hp_threshold: float = 0.01) -> bool:
    """
    Жив, если доля HP выше порога. Порог совпадает с revive-логикой.
    """
    try:
        return float(getattr(state, "hp_ratio", 0.0)) > float(zero_hp_threshold)
    except Exception:
        return False

class PlayerStateMonitor:
    def __init__(
            self,
            server: str,
            get_window: Callable[[], Optional[Dict]],
            on_update: Optional[Callable[[PlayerState], None]] = None,
            poll_interval: float = 1,
            debug: bool = False,
            custom_capture: Optional[Callable[[Dict, tuple], Optional[np.ndarray]]] = None,
    ):
        self.server = server
        self._get_window = get_window
        self._on_update = on_update
        self.poll_interval = max(1, float(poll_interval))
        self.debug = debug
        self._capture = custom_capture or capture_window_region_bgr

        self._zones = {}
        self._colors_alive = []
        self._colors_dead = []
        self._tol = 3
        self._load_state_config(server)

        self._running = False
        self._thr: Optional[threading.Thread] = None
        self._last = PlayerState()

    def set_server(self, server: str):
        self.server = server
        self._load_state_config(server)

    def start(self):
        if self._running:
            return
        self._running = True
        self._thr = threading.Thread(target=self._loop, daemon=True)
        self._thr.start()

    def stop(self):
        self._running = False

    def last(self) -> PlayerState:
        return self._last

    # -------- internals --------
    def _load_state_config(self, server: str):
        try:
            mod = importlib.import_module(f"core.servers.{server}.zones.state")
            self._zones = getattr(mod, "ZONES", {})
            colors = getattr(mod, "COLORS", {})
            self._colors_alive = colors.get("hp_alive_rgb", [])
            self._colors_dead = colors.get("hp_dead_rgb", [])
            self._tol = int(getattr(mod, "HP_COLOR_TOLERANCE", 3))
        except Exception as e:
            print(f"[state] load fail: {e}")
            self._zones = {}
            self._colors_alive = []
            self._colors_dead = []
            self._tol = 3

    def _loop(self):
        while self._running:
            try:
                win = self._get_window() or {}
                zone = self._zones.get("state")
                if zone and (self._colors_alive or self._colors_dead):
                    hp_ratio = self._compute_hp_ratio(win, zone)
                else:
                    hp_ratio = 1.0
                st = PlayerState(hp_ratio=float(hp_ratio), cp_ratio=1.0, ts=time.time())
                self._last = st
                if self._on_update:
                    try:
                        self._on_update(st)
                    except Exception:
                        pass
                if self.debug:
                    print(f"[state] hp={st.hp_ratio:.3f}")
            except Exception as e:
                if self.debug:
                    print(f"[state] loop error: {e}")
            time.sleep(self.poll_interval)

    def _compute_hp_ratio(self, window: Dict, zone: tuple) -> float:
        img = self._capture(window, zone)
        if img is None or img.size == 0:
            return self._last.hp_ratio  # нет картинки — сохраняем предыдущую оценку

        alive_mask = mask_for_colors_bgr(img, self._colors_alive, tol=self._tol) if self._colors_alive else None
        dead_mask  = mask_for_colors_bgr(img, self._colors_dead,  tol=self._tol) if self._colors_dead  else None

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
                return a_area / total if total > 0 else self._last.hp_ratio
            return a_w / total

        if alive_mask is not None:
            a_area = int(np.count_nonzero(alive_mask))
            total = img.shape[0] * img.shape[1]
            return a_area / total if total > 0 else self._last.hp_ratio

        if dead_mask is not None:
            d_area = int(np.count_nonzero(dead_mask))
            total = img.shape[0] * img.shape[1]
            return 1.0 - (d_area / total if total > 0 else 0.0)

        return self._last.hp_ratio
