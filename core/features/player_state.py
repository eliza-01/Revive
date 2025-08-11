# core/features/player_state.py
# Монитор состояния персонажа: HP (пока только по цветам).
# Зоны и цвета берём из модулей:
#   core.servers.<server>.zones.state -> ZONES["state"]
#   core.servers.<server>.colors.state -> COLORS["hp"] = [(low_rgb, high_rgb), ...]
import importlib
import threading
import time
from typing import Callable, Optional, Dict

from core.vision.colors import sample_ratio_in_zone

class PlayerState:
    __slots__ = ("hp_ratio", "cp_ratio", "ts")
    def __init__(self, hp_ratio: float = 1.0, cp_ratio: float = 1.0, ts: float = 0.0):
        self.hp_ratio = hp_ratio
        self.cp_ratio = cp_ratio
        self.ts = ts

class PlayerStateMonitor:
    def __init__(
            self,
            server: str,
            get_window: Callable[[], Optional[Dict]],
            on_update: Optional[Callable[[PlayerState], None]] = None,
            poll_interval: float = 0.2,
            debug: bool = False,
    ):
        self.server = server
        self._get_window = get_window
        self._on_update = on_update
        self.poll_interval = max(0.05, float(poll_interval))
        self.debug = debug

        self._zones = {}
        self._colors = {}
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
        # zones
        try:
            zones_mod = importlib.import_module(f"core.servers.{server}.zones.state")
            self._zones = getattr(zones_mod, "ZONES", {})
        except Exception as e:
            print(f"[state] zones load fail: {e}")
            self._zones = {}
        # colors
        try:
            colors_mod = importlib.import_module(f"core.servers.{server}.colors.state")
            self._colors = getattr(colors_mod, "COLORS", {})
        except Exception as e:
            print(f"[state] colors load fail: {e}")
            self._colors = {}

    def _loop(self):
        while self._running:
            try:
                win = self._get_window() or {}
                zone = self._zones.get("state")
                hp_ranges = self._colors.get("hp", [])
                if zone and hp_ranges:
                    hp = sample_ratio_in_zone(win, zone, hp_ranges)
                else:
                    hp = 1.0
                st = PlayerState(hp_ratio=float(hp), cp_ratio=1.0, ts=time.time())
                self._last = st
                if self._on_update:
                    try:
                        self._on_update(st)
                    except Exception:
                        pass
                if self.debug:
                    print(f"[state] hp={st.hp_ratio:.2f}")
            except Exception as e:
                if self.debug:
                    print(f"[state] loop error: {e}")
            time.sleep(self.poll_interval)
