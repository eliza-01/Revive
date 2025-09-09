# app/launcher/sections/respawn.py
from __future__ import annotations
from typing import Dict
from ..base import BaseSection
from core.state.pool import pool_write, pool_get

class RespawnSection(BaseSection):
    """
    Управление настройками респавна:
      - включение/выключение авто-респавна
      - "ждать возрождения" и таймаут ожидания (сек)
    Примечание: в respawn_get_wait_config поле 'enabled' — это именно wait_enabled (как в старом API).
    """

    def __init__(self, window, state):
        super().__init__(window, state)
        # дефолты уже в пуле (ensure_pool); тут ничего дополнительно не пишем

    # --- helpers ---
    def _cfg(self) -> dict:
        return {
            "enabled": bool(pool_get(self.s, "features.respawn.wait_enabled", False)),
            "seconds": int(pool_get(self.s, "features.respawn.wait_seconds", 120)),
            "respawn_enabled": bool(pool_get(self.s, "features.respawn.enabled", False)),
        }

    # --- API: setters ---
    def respawn_set_enabled(self, enabled: bool):
        val = bool(enabled)
        pool_write(self.s, "features.respawn", {"enabled": val})
        self.emit("respawn", f"Авто-респавн: {'вкл' if val else 'выкл'}", True if val else None)

    def respawn_set_wait_enabled(self, enabled: bool):
        val = bool(enabled)
        pool_write(self.s, "features.respawn", {"wait_enabled": val})
        self.emit("respawn", f"Ждать возрождения: {'да' if val else 'нет'}", None)

    def respawn_set_wait_seconds(self, seconds: int):
        try:
            val = max(0, int(seconds or 0))
        except Exception:
            val = 0
        pool_write(self.s, "features.respawn", {"wait_seconds": val})
        self.emit("respawn", f"Таймаут ожидания: {val} сек.", None)

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
