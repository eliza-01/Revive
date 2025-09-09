# core/engines/window_focus/service.py
#core/engines/window_focus/service.py
from __future__ import annotations
from typing import Callable, Optional, Dict, Any
import threading, time

from core.engines.window_focus.runner import run_window_focus


class WindowFocusService:
    """
    Фоновый сервис проверки фокуса окна.
    Обновляет состояние через on_update.
    Интерфейс: is_running(), start(poll_interval=2.0), stop()

    ВНИМАНИЕ: сервис сам НЕ пишет ничего в пул.
    Выставление services.window_focus.running делается снаружи (в wiring).
    """

    def __init__(
        self,
        get_window: Callable[[], Optional[Dict[str, Any]]],
        on_update: Optional[Callable[[Dict[str, Any]], None]] = None,
        on_status: Optional[Callable[[str, Optional[bool]], None]] = None,
    ):
        self._get_window = get_window
        self._on_update = on_update
        self._on_status = on_status or (lambda *_: None)
        self._run = False
        self._thr: Optional[threading.Thread] = None

    def is_running(self) -> bool:
        return bool(self._run)

    def start(self, poll_interval: float = 2.0):
        if self._run:
            return
        self._run = True

        def loop():
            try:
                while self._run:
                    try:
                        run_window_focus(
                            server="common",
                            get_window=self._get_window,
                            on_status=lambda *_: None,
                            on_update=self._on_update,
                            cfg={"poll_interval": poll_interval},
                            should_abort=lambda: (not self._run),
                        )
                    except Exception:
                        pass
                    time.sleep(0.05)
            finally:
                self._run = False

        self._thr = threading.Thread(target=loop, daemon=True)
        self._thr.start()

    def stop(self):
        self._run = False
