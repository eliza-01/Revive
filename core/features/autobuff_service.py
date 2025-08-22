# core/features/autobuff_service.py
from __future__ import annotations
from typing import Callable, Optional

from core.runtime.poller import RepeaterThread


class AutobuffService:
    """
    Периодическая проверка «заряженности» + автобаф по интервалу.
    Никаких зависимостей от Tk или UI — всё через коллбэки.
    """

    def __init__(
        self,
        *,
        checker,                                # core.checks.charged.ChargeChecker
        is_alive: Callable[[], bool],
        buff_is_enabled: Callable[[], bool],
        buff_run_once: Callable[[], bool],
        on_charged_update: Optional[Callable[[Optional[bool]], None]] = None,
        tick_interval_s: float = 1.0,
        log=print,
    ):
        self.checker = checker
        self.is_alive = is_alive
        self.buff_is_enabled = buff_is_enabled
        self.buff_run_once = buff_run_once
        self.on_charged_update = on_charged_update or (lambda *_: None)
        self._log = log

        self._enabled = False
        self._poller = RepeaterThread(fn=self._tick, interval=float(tick_interval_s), debug=False)
        self._poller.start()

    def set_enabled(self, enabled: bool):
        self._enabled = bool(enabled)

    def stop(self):
        try:
            self._poller.stop()
        except Exception:
            pass

    # --- internals ---
    def _tick(self):
        if not self._enabled or not self.is_alive():
            return
        try:
            if not self.checker.tick():
                return

            cur = self.checker.is_charged(None)
            self._log(f"[charged] interval → {cur}")
            if cur is True:
                self.on_charged_update(True)
                return

            # False/None → пробуем баф, если включён
            if self.buff_is_enabled():
                ok = bool(self.buff_run_once())
                self._log(f"[buff] interval autobuff run: {ok}")
                if ok:
                    new_val = self.checker.force_check()
                    self.on_charged_update(bool(new_val))
                    self._log(f"[charged] after buff → {new_val}")
        except Exception as e:
            self._log(f"[autobuff] tick error: {e}")
