# engines/respawn/runner.py
from __future__ import annotations
from typing import Callable, Optional, Dict

class RespawnRunner:
    """
    Обёртка над конкретным server-движком respawn.
    Движок должен реализовать:
      - set_server(server: str) -> None
      - run_stand_up_once(window: Dict, lang: str, timeout_ms: int) -> bool
    """

    def __init__(
        self,
        engine,  # engines.respawn.server.<server>.engine.create_engine(...)
        get_window: Callable[[], Optional[Dict]],
        get_language: Callable[[], str],
    ):
        self.engine = engine
        self._get_window = get_window
        self._get_language = get_language

    def set_server(self, server: str) -> None:
        self.engine.set_server(server)

    def run(self, timeout_ms: int = 14_000) -> bool:
        """Запускает сценарий подъёма (stand_up)."""
        win = self._get_window() or {}
        if not win:
            print("[respawn] no window")
            return False
        lang = (self._get_language() or "rus").lower()
        return self.engine.run_stand_up_once(win, lang, timeout_ms=timeout_ms)
