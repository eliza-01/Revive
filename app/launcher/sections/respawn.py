# app/launcher/sections/respawn.py
from __future__ import annotations
from .base import BaseSection

class RespawnSection(BaseSection):
    def __init__(self, window, controller, watcher, orch, sys_state, schedule):
        super().__init__(window, sys_state)
        self.controller = controller
        self.watcher = watcher
        self.orch = orch
        self.schedule = schedule

    def respawn_set_monitoring(self, enabled: bool):
        if enabled and not self.watcher.is_running():
            self.watcher.start(); self.emit("watcher", "Мониторинг: вкл", True)
        elif not enabled and self.watcher.is_running():
            self.watcher.stop();  self.emit("watcher", "Мониторинг: выкл", None)

    def respawn_set_enabled(self, enabled: bool):
        self.s["respawn_enabled"] = bool(enabled)

    def watcher_is_running(self) -> bool:
        return bool(self.watcher.is_running())

    def expose(self) -> dict:
        return {
            "respawn_set_monitoring": self.respawn_set_monitoring,
            "respawn_set_enabled": self.respawn_set_enabled,
            "watcher_is_running": self.watcher_is_running,
        }
