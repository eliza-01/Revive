from __future__ import annotations
from typing import Callable, Optional, Dict, Any
import threading, time

from core.engines.player_state.runner import run_player_state


class PlayerStateService:
    """
    Фоновый сервис опроса HP.
    НИЧЕГО не пишет в пул сам по себе — только вызывает колбэки.
    Интерфейс: is_running(), start(poll_interval=0.25), stop()
    """

    def __init__(
        self,
        server: Callable[[], str],
        get_window: Callable[[], Optional[Dict[str, Any]]],
        on_update: Optional[Callable[[Dict[str, Any]], None]] = None,
    ):
        self._server = server
        self._get_window = get_window
        self._on_update = on_update
        self._run = False
        self._thr: Optional[threading.Thread] = None

    def is_running(self) -> bool:
        return bool(self._run)

    def start(self, poll_interval: float = 1):
        if self._run:
            return
        self._run = True

        def loop():
            try:
                while self._run:
                    try:
                        run_player_state(
                            server=self._server() or "boh",
                            get_window=self._get_window,
                            on_update=self._on_update,
                            cfg={"poll_interval": poll_interval},
                            should_abort=lambda: (not self._run),
                        )
                    except Exception:
                        # глушим исключения цикла опроса и пробуем перезапуститься
                        pass
                    time.sleep(0.05)  # пауза между перезапусками
            finally:
                self._run = False

        self._thr = threading.Thread(target=loop, daemon=True)
        self._thr.start()

    def stop(self):
        self._run = False
