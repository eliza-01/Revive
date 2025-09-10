# core/engines/ui_guard/runner.py
from __future__ import annotations
from typing import Callable, Optional, Dict, Any

class UIGuardRunner:
    """
    Одноразовая проверка экрана: найти открытую страницу и попытаться закрыть.
    """
    def __init__(
        self,
        engine: Any,
        get_window: Callable[[], Optional[Dict]],
        get_language: Callable[[], str],
        report: Optional[Callable[[str], None]] = None,
    ):
        self.engine = engine
        self._get_window = get_window
        self._get_language = get_language
        self._report = report or (lambda *_: None)

    def run_once(self) -> Dict[str, Any]:
        win = self._get_window() or {}
        if not win:
            self._report("[UI_GUARD] no window")
            return {"found": False}

        lang = (self._get_language() or "rus").lower()
        self._report("[UI_GUARD] scan start…")

        page = self.engine.scan_open_page(win, lang)
        if not page:
            # для наглядности — чтобы видеть, что тикер живёт
            self._report("[UI_GUARD] no overlays")
            return {"found": False}

        key, pt = page["key"], page["pt"]
        self._report(f"[UI_GUARD] detected page: {key} @ {pt}")

        closed = self.engine.try_close(win, lang, key)
        self._report(f"[UI_GUARD] close {'OK' if closed else 'FAIL'}: {key}")

        return {"found": True, "key": key, "closed": bool(closed)}
