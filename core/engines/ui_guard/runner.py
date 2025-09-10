# core/engines/ui_guard/runner.py
from __future__ import annotations
from typing import Callable, Optional, Dict, Any

class UIGuardRunner:
    """
    Одноразовый запуск UI-стража:
      - ищет открытую страницу/оверлей,
      - пытается закрыть,
      - если закрыл — сразу снова ищет (пока экран не станет чистым).
    Возвращает словарь-итог:
      {"found": bool, "closed": bool, "key": <последняя найденная или 'empty'>}
    """

    def __init__(
        self,
        engine: Any,
        get_window: Callable[[], Optional[Dict[str, Any]]],
        get_language: Callable[[], str],
        report: Optional[Callable[[str], None]] = None,
        *,
        is_focused: Optional[Callable[[], bool]] = None,   # <— добавлено
    ):
        self.engine = engine
        self._get_window = get_window
        self._get_language = get_language
        self._report = report or (lambda *_: None)
        self._is_focused = is_focused or (lambda: True)

    def _log(self, msg: str) -> None:
        try:
            self._report(str(msg))
        except Exception:
            pass

    def run_once(self) -> Dict[str, Any]:
        # если фокуса нет — ничего не делаем
        try:
            if not self._is_focused():
                self._log("[UI_GUARD] skip: no focus")
                return {"found": False, "closed": False, "key": ""}
        except Exception:
            # в сомнительных ситуациях лучше не блокировать
            pass

        win = self._get_window() or {}
        if not win:
            self._log("[UI_GUARD] no window")
            return {"found": False, "closed": False, "key": ""}

        lang = (self._get_language() or "rus").lower()

        closed_any = False

        while True:
            found = self.engine.scan_open_page(win, lang)
            if not found:
                if closed_any:
                    self._log("[UI_GUARD] screen clear")
                return {
                    "found": closed_any,
                    "closed": closed_any,
                    "key": "empty" if closed_any else ""
                }

            page_key = str(found.get("key") or "")
            self._log(f"[UI_GUARD] found {page_key}")

            ok = self.engine.try_close(win, lang, page_key)
            if not ok:
                self._log(f"[UI_GUARD] cannot close {page_key}")
                return {"found": True, "closed": closed_any, "key": page_key}

            closed_any = True
            # цикл продолжается — сразу проверяем, не остались ли ещё страницы
