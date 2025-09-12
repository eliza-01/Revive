# core/engines/player_state/watcher.py
from __future__ import annotations
import threading, time
from typing import Callable, Optional, Dict, Any

from core.engines.player_state.server.l2mad import engine as ps_boh


class PlayerStateWatcher:
    def __init__(self, server: str, get_window: Callable[[], dict]):
        self.server = (server or "boh").lower()
        self.get_window = get_window
        self._running = False
        self._th = None
        self.last = {"hp_ratio": 1.0, "ts": 0.0}

    def _on_update(self, data: Dict[str, Any]):
        self.last.update(data)

    def is_running(self) -> bool:
        return self._running

    def start(self, poll_interval: float = 0.5):
        if self._running: return
        self._running = True
        def loop():
            ctx = {
                "get_window": self.get_window,
                "on_update": self._on_update,
                "should_abort": lambda: not self._running,
            }
            cfg = {"poll_interval": poll_interval}
            try:
                ps_boh.start(ctx, cfg)
            finally:
                self._running = False
        self._th = threading.Thread(target=loop, daemon=True)
        self._th.start()

    def stop(self):
        self._running = False
