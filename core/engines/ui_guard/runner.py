from __future__ import annotations
from typing import Callable, Optional, Dict, Any

class UIGuardRunner:
    """
    Одноразовый прогон: найти открытую страницу и закрыть.
    """
    def __init__(self, engine: Any, get_window: Callable[[], Optional[Dict]], get_language: Callable[[], str], report: Callable[[str], None]):
        self.engine = engine
        self._get_window = get_window
        self._get_language = get_language
        self._report = report or (lambda _m: None)

    def run_once(self) -> Dict[str, Any]:
        win = self._get_window() or {}
        if not win:
            self._report("[UI_GUARD] no window")
            return {"found": False}

        lang = (self._get_language() or "rus").lower()
        found = self.engine.scan_open_page(win, lang)

        if not found:
            self._report("[UI_GUARD] no overlays")
            return {"found": False}

        key = found.get("key", "")
        self._report(f"[UI_GUARD] overlay detected: {key}")
        closed = bool(self.engine.try_close(win, lang, key))
        return {"found": True, "key": key, "closed": closed}
