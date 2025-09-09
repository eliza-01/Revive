# app/launcher/sections/state.py
from __future__ import annotations
from typing import Optional
from ..base import BaseSection
from core.state.pool import pool_write

class StateSection(BaseSection):
    """
    Мониторинг (watcher): старт/стоп опроса состояния игрока.
    """
    def __init__(self, window, watcher, state):
        super().__init__(window, state)
        self.watcher = watcher

    def watcher_set_enabled(self, enabled: bool):
        if enabled and not self.watcher.is_running():
            self.watcher.start()
            pool_write(self.s, "services.player_state", {"running": True})
            self.emit("watcher", "Мониторинг: вкл", True)
        elif (not enabled) and self.watcher.is_running():
            self.watcher.stop()
            pool_write(self.s, "services.player_state", {"running": False})
            self.emit("watcher", "Мониторинг: выкл", None)

    def watcher_is_running(self) -> bool:
        return bool(self.watcher.is_running())

    def expose(self) -> dict:
        return {
            "watcher_set_enabled": self.watcher_set_enabled,
            "watcher_is_running": self.watcher_is_running,
        }
