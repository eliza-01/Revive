from __future__ import annotations
from typing import Callable, Optional, Dict

class RespawnRunner:
    """
    Обёртка над server-движком respawn.
    Требуемые методы движка:
      - set_server(server: str) -> None
      - run_stand_up_once(window: Dict, lang: str, timeout_ms: int) -> bool
      - run_procedure(window: Dict, lang: str, mode: str, wait_seconds: int, total_timeout_ms: int) -> bool
    """

    def __init__(
        self,
        engine,
        get_window: Callable[[], Optional[Dict]],
        get_language: Callable[[], str],
    ):
        self.engine = engine
        self._get_window = get_window
        self._get_language = get_language

    def set_server(self, server: str) -> None:
        self.engine.set_server(server)

    def run(self, mode: str = "auto", wait_seconds: int = 0, total_timeout_ms: int = 14_000) -> bool:
        """Запуск процедуры респавна согласно режиму."""
        win = self._get_window() or {}
        if not win:
            print("[respawn] no window")
            return False
        lang = (self._get_language() or "rus").lower()
        try:
            return bool(self.engine.run_procedure(
                window=win,
                lang=lang,
                mode=mode,
                wait_seconds=wait_seconds,
                total_timeout_ms=total_timeout_ms,
            ))
        except AttributeError:
            # fallback на старый API
            return bool(self.engine.run_stand_up_once(win, lang, timeout_ms=total_timeout_ms))
