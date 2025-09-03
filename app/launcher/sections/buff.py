# app/launcher/sections/buff.py
from __future__ import annotations
from .base import BaseSection

class BuffSection(BaseSection):
    def __init__(self, window, controller, watcher, sys_state, schedule, system_section=None):
        super().__init__(window, sys_state)
        self.controller = controller
        self.watcher = watcher
        self.schedule = schedule
        self.system = system_section
        self._worker = None

        # зарегистрировать делегат для AutobuffService
        if self.system and hasattr(self.system, "set_buff_run_once_delegate"):
            self.system.set_buff_run_once_delegate(self.buff_run_once)

    def _ensure_worker(self):
        from core.features.buff_after_respawn import BuffAfterRespawnWorker
        if not self._worker:
            self._worker = BuffAfterRespawnWorker(
                controller=self.controller,
                server=self.s["server"],
                get_window=lambda: self.s.get("window"),
                get_language=lambda: self.s["language"],
                on_status=lambda t, ok=None: self.emit("buff", t, ok),
                click_threshold=0.87, debug=True,
            )
        # синхронизируем динамику каждый вызов
        self._worker.server = self.s["server"]
        try:
            # если хочешь — здесь же устанавливай режим/метод
            if self.s.get("buff_mode"):
                self._worker.set_mode(self.s["buff_mode"])
            if self.s.get("buff_method"):
                self._worker.set_method(self.s["buff_method"])
        except Exception:
            pass
        return self._worker

    def buff_set_enabled(self, enabled: bool):
        self.s["buff_enabled"] = bool(enabled)

    def buff_set_mode(self, mode: str):
        self.s["buff_mode"] = (mode or "profile").lower()

    def buff_set_method(self, method: str):
        self.s["buff_method"] = method or ""
        try:
            prof = self.s["profile"]
            if hasattr(prof, "set_buff_mode"):
                prof.set_buff_mode(self.s["buff_method"])
        except Exception:
            pass

    def buff_run_once(self) -> bool:
        if not self.s.get("window"):
            self.emit("buff", "Окно не найдено", False); return False
        ok = self._ensure_worker().run_once()
        self.emit("buff", "Баф выполнен" if ok else "Баф не выполнен", ok)
        return bool(ok)

    def expose(self) -> dict:
        return {
            "buff_set_enabled": self.buff_set_enabled,
            "buff_set_mode": self.buff_set_mode,
            "buff_set_method": self.buff_set_method,
            "buff_run_once": self.buff_run_once,
        }
