# app/launcher/sections/respawn.py
from __future__ import annotations
from ..base import BaseSection

class RespawnSection(BaseSection):
    """
    Только управление настройками респавна:
      - включение/выключение авто-респавна
      - "ждать возрождения" и таймаут ожидания (сек)
    """
    def __init__(self, window, sys_state):
        super().__init__(window, sys_state)
        # дефолты, если не заданы
        self.s.setdefault("respawn_enabled", False)
        self.s.setdefault("respawn_wait_enabled", False)
        self.s.setdefault("respawn_wait_seconds", 120)

    # --- helpers ---
    def _cfg(self) -> dict:
        return {
            "enabled": bool(self.s.get("respawn_wait_enabled", False)),
            "seconds": int(self.s.get("respawn_wait_seconds", 120)),
            "respawn_enabled": bool(self.s.get("respawn_enabled", False)),
        }

    # --- API: setters ---
    def respawn_set_enabled(self, enabled: bool):
        self.s["respawn_enabled"] = bool(enabled)
        self.emit("respawn", "Авто-респавн: вкл" if enabled else "Авто-респавн: выкл",
                  True if enabled else None)

    def respawn_set_wait_enabled(self, enabled: bool):
        self.s["respawn_wait_enabled"] = bool(enabled)
        self.emit("respawn", "Ждать возрождения: да" if enabled else "Ждать возрождения: нет", None)

    def respawn_set_wait_seconds(self, seconds: int):
        try:
            val = max(0, int(seconds or 0))
        except Exception:
            val = 0
        self.s["respawn_wait_seconds"] = val
        self.emit("respawn", f"Таймаут ожидания возрождения: {val} сек.", None)

    # --- API: getters ---
    def respawn_get_wait_config(self) -> dict:
        """Отдать текущие настройки ожидания (для UI init/refresh)."""
        return self._cfg()

    def expose(self) -> dict:
        return {
            "respawn_set_enabled": self.respawn_set_enabled,
            "respawn_set_wait_enabled": self.respawn_set_wait_enabled,
            "respawn_set_wait_seconds": self.respawn_set_wait_seconds,
            "respawn_get_wait_config": self.respawn_get_wait_config,
        }
