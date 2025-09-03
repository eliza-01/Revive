# app/launcher/sections/autofarm.py
from __future__ import annotations
from typing import Any, Dict
from .base import BaseSection
from core.engines.autofarm.service import AutoFarmService
from core.engines.autofarm.runner import run_autofarm

class AutofarmSection(BaseSection):
    def __init__(self, window, controller, watcher, sys_state, schedule):
        super().__init__(window, sys_state)
        self.controller = controller
        self.watcher = watcher
        self.schedule = schedule

        self.service = AutoFarmService(
            controller=self.controller,
            get_server=lambda: self.s["server"],
            get_language=lambda: self.s["language"],
            get_window=lambda: self.s.get("window"),
            is_alive=lambda: self.watcher.is_alive(),
            schedule=self._schedule,
            on_status=lambda text, ok=None: self.emit("af", text, ok),
            log=print,
        )

        # по умолчанию
        self._cfg: Dict[str, Any] = {}   # {profession, skills:[{key,slug,cast_ms}], zone, monsters:[...]}
        self._mode = "after_tp"

    def _schedule(self, fn, ms: int):
        self.schedule(fn, ms)

    # --- API для UI ---
    def autofarm_set_mode(self, mode: str):
        self._mode = (mode or "after_tp").lower()
        self.service.set_mode(self._mode)

    def autofarm_set_enabled(self, enabled: bool):
        self.service.set_enabled(bool(enabled), cfg=self._cfg)
        self.emit("af", "Включено" if enabled else "Выключено", True if enabled else None)

    def autofarm_validate(self, ui_state: Dict[str, Any]):
        ok = True; reason = None
        if not ui_state.get("profession"):
            ok, reason = False, "Выберите профессию"
        elif not any((s.get("slug") for s in (ui_state.get("skills") or []))):
            ok, reason = False, "Добавьте атакующий скилл"
        elif not ui_state.get("zone"):
            ok, reason = False, "Выберите зону"
        return {"ok": ok, "reason": reason}

    def autofarm_save(self, ui_state: Dict[str, Any]):
        self._cfg = dict(ui_state or {})
        # обновляем в сервисе, но не трогаем enabled
        self.service.set_enabled(self.service.enabled, cfg=self._cfg)
        return {"ok": True}

    # ручной старт (если UI такое вызывает)
    def af_start(self, mode: str = "after_tp") -> bool:
        def _st(msg, ok=None): self.emit("af", f"[AF] {msg}", ok)
        return run_autofarm(
            server=self.s["server"],
            controller=self.controller,
            get_window=lambda: self.s.get("window"),
            get_language=lambda: self.s["language"],
            on_status=_st,
            cfg=self._cfg,
        )

    # «вооружить» после ТП — внешняя точка, если нужна
    def arm_after_tp(self):
        try:
            if self.service.enabled and self._mode == "after_tp":
                self.service.arm()
        except Exception as e:
            self.emit("af", f"[AF] arm after TP failed: {e}", False)

    def expose(self) -> dict:
        return {
            "autofarm_set_mode": self.autofarm_set_mode,
            "autofarm_set_enabled": self.autofarm_set_enabled,
            "autofarm_validate": self.autofarm_validate,
            "autofarm_save": self.autofarm_save,
            "af_start": self.af_start,
        }
