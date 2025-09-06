# app/launcher/sections/state.py
from __future__ import annotations
from ..base import BaseSection

class StateSection(BaseSection):
    """
    Мониторинг (watcher): старт/стоп отслеживания состояния игрока.
    НИКАКОГО респавна здесь.
    """
    def __init__(self, window, watcher, sys_state):
        super().__init__(window, sys_state)
        self.watcher = watcher

    # watcher — это сервис нового player_state с методами is_running/start/stop
    def watcher_set_enabled(self, enabled: bool):
        if enabled and not self.watcher.is_running():
            self.watcher.start()
            self.emit("watcher", "Мониторинг: вкл", True)
        elif (not enabled) and self.watcher.is_running():
            self.watcher.stop()
            self.emit("watcher", "Мониторинг: выкл", None)

    def watcher_is_running(self) -> bool:
        return bool(self.watcher.is_running())

    def expose(self) -> dict:
        return {
            "watcher_set_enabled": self.watcher_set_enabled,
            "watcher_is_running": self.watcher_is_running,
        }
