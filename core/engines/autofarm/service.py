# core/engines/autofarm/service.py
from __future__ import annotations
import importlib, time
from typing import Callable, Dict, Any, Optional
from core.runtime.poller import RepeaterThread
from core.runtime.dashboard_guard import DASHBOARD_GUARD

class AutoFarmService:
    def __init__(self, controller, get_server, get_language, get_window, is_alive,
                 schedule=None, on_status=lambda *_: None,
                 is_dashboard_busy=lambda: DASHBOARD_GUARD.is_busy(), log=None, **_):
        self.controller = controller
        self.get_server = get_server
        self.get_language = get_language
        self.get_window = get_window
        self.is_alive = is_alive
        self.schedule = schedule or (lambda fn, ms: None)
        self.on_status = on_status
        self.is_dashboard_busy = is_dashboard_busy
        self._log = log or (lambda *a, **k: None)

        self.enabled = False
        self.mode = "after_tp"
        self._armed = False
        self._cfg: Dict[str, Any] = {}
        self._poll = RepeaterThread(self._tick, 0.5)

    # ← НОВОЕ
    def arm(self):
        """Вооружить автозапуск АФ (после завершения post-TP)."""
        if self.enabled and self.mode == "after_tp":
            self._armed = True
            self._idle_since = 0.0
            if not self._poll.is_running():
                self._poll.start()

    # Совместимость: вызывается из Bridge._on_alive_proxy(); ничего не делаем.
    def notify_after_tp(self):
        return None

    def notify_after_tp(self):
        """Совместимость со старым кодом: ничего не делаем.
        Вооружение выполняется явным arm() из post-TP on_finished."""
        return

    def start(self, cfg: Dict[str, Any]) -> bool:
        server = (self.get_server() or "l2mad").lower()
        try:
            mod = importlib.import_module(f"core.engines.autofarm.{server}.engine")
        except Exception as e:
            self.on_status(f"[af] engine import error: {e}", False); return False
        ctx = {"server": server, "controller": self.controller,
               "get_window": self.get_window, "get_language": self.get_language,
               "on_status": self.on_status}
        try:
            ok = bool(mod.start(ctx, cfg or {}))
            self.on_status("Автофарм запущен" if ok else "Автофарм не запущен", True if ok else False)
            return ok
        except Exception as e:
            self.on_status(f"[af] start error: {e}", False); return False

    def set_enabled(self, v: bool, cfg: Optional[Dict[str, Any]] = None):
        self.enabled = bool(v)
        if cfg is not None:
            self._cfg = dict(cfg)

        if not self.enabled:
            self._armed = False
            self._idle_since = 0.0
            return

        if self.mode == "manual":
            self.start(self._cfg)
        else:
            # after_tp: НЕ вооружаемся сразу, ждём явного arm() после ТП/маршрута
            self._armed = False
            self._idle_since = 0.0

        if not self._poll.is_running():
            self._poll.start()

    def set_mode(self, mode: str):
        self.mode = (mode or "after_tp").lower()
        # В after_tp не вооружаемся автоматически
        if self.mode == "after_tp":
            self._armed = False
            self._idle_since = 0.0

    _idle_since = 0.0
    def _tick(self):
        if not (self.enabled and self._armed): return
        if not self.is_alive(): self._idle_since = 0.0; return
        if self.is_dashboard_busy(): self._idle_since = 0.0; return
        now = time.time()
        if self._idle_since == 0.0: self._idle_since = now; return
        if (now - self._idle_since) >= 1.5:
            self._armed = False
            self.start(self._cfg)

    # --- шими для совместимости со старым кодом ---
    def register_pre_step(self, *_, **__):
        """Игнорируем регистрацию прешагов (совместимость)."""
        return None

    def unregister_pre_step(self, *_, **__):
        return None

    def register_post_step(self, *_, **__):
        return None

    def unregister_post_step(self, *_, **__):
        return None
    # --- конец шимов ---
