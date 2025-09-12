# core/engines/respawn/runner.py
from __future__ import annotations
from typing import Callable, Optional, Dict, Any

from core.logging import console


class RespawnRunner:
    """
    Обёртка над server-движком respawn.

    Требуемые методы движка:
      - set_server(server: str) -> None
      - run_stand_up_once(window: Dict, lang: str, timeout_ms: int) -> bool

    НИКАКОЙ обратной совместимости: вызываем только run_stand_up_once().
    """

    def __init__(
        self,
        engine: Any,
        get_window: Callable[[], Optional[Dict]],
        get_language: Callable[[], str],
    ):
        self.engine = engine
        self._get_window = get_window
        self._get_language = get_language

    def set_server(self, server: str) -> None:
        self.engine.set_server(server)

    def run(
        self,
        mode: str = "auto",          # оставлено в сигнатуре для совместимости вызовов, не используется
        wait_seconds: int = 0,       # оставлено в сигнатуре для совместимости вызовов, не используется
        total_timeout_ms: int = 14_000,
        **_kwargs,                   # игнорируем любые дополнительные ключи
    ) -> bool:
        """
        Запуск процедуры респавна через движок:
        строго вызываем engine.run_stand_up_once(window, lang, timeout_ms=...).
        """
        win = self._get_window() or {}
        if not win:
            console.log("[respawn] no window")
            return False

        lang = (self._get_language() or "rus").lower()

        return bool(
            self.engine.run_stand_up_once(
                window=win,
                lang=lang,
                timeout_ms=int(total_timeout_ms),
            )
        )
