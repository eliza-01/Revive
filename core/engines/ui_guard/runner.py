# core/engines/ui_guard/runner.py
from __future__ import annotations
from typing import Callable, Optional, Dict, Any

from core.logging import console
from core.state.pool import pool_write


class UIGuardRunner:
    """
    Одноразовый запуск UI-стража:
      - СНАЧАЛА закрывает страницы (крестики),
      - затем проверяет и обрабатывает блокеры,
      - повторяет цикл, пока экран не станет чистым.
    Возвращает итог:
      {"found": bool, "closed": bool, "key": <последняя найденная или 'empty'>}
    """

    def __init__(
        self,
        engine: Any,
        get_window: Callable[[], Optional[Dict[str, Any]]],
        get_language: Callable[[], str],
        *,
        is_focused: Optional[Callable[[], bool]] = None,   # только фокус, без report/on_status
        state: Optional[Dict[str, Any]] = None,            # ← для записи в pool (features.ui_guard)
    ):
        self.engine = engine
        self._get_window = get_window
        self._get_language = get_language
        self._is_focused = is_focused or (lambda: True)
        self._state = state or None

    # ---- pool helpers ----------------------------------------------------
    def _pool_set(self, busy: Optional[bool] = None, report: Optional[str] = None) -> None:
        if self._state is None:
            return
        data: Dict[str, Any] = {}
        if busy is not None:
            data["busy"] = bool(busy)
        if report is not None:
            data["report"] = str(report)
        if data:
            try:
                pool_write(self._state, "features.ui_guard", data)
            except Exception:
                pass

    # ---- main ------------------------------------------------------------
    def run_once(self) -> Dict[str, Any]:
        # старт: отмечаем busy=True
        self._pool_set(busy=True)

        # если фокуса нет — не работаем
        try:
            if not self._is_focused():
                console.hud("err", "[UI_GUARD] skip: no focus")
                self._pool_set(busy=False, report="idle")
                return {"found": False, "closed": False, "key": ""}
        except Exception:
            # в сомнительных ситуациях лучше не блокировать, но busy снимем
            self._pool_set(busy=False, report="idle")
            return {"found": False, "closed": False, "key": ""}

        win = self._get_window() or {}
        if not win:
            console.hud("err", "[UI_GUARD] no window")
            self._pool_set(busy=False, report="idle")
            return {"found": False, "closed": False, "key": ""}

        lang = (self._get_language() or "rus").lower()
        closed_any = False

        while True:
            # 1) Страницы (оверлеи) — закрываем крестики
            found = self.engine.scan_open_page(win, lang)
            if found:
                page_key = str(found.get("key") or "")
                self._pool_set(report="page")
                console.hud("ok", f"[UI_GUARD] found {page_key}")
                ok = self.engine.try_close(win, lang, page_key)
                if not ok:
                    console.hud("err", f"[UI_GUARD] cannot close {page_key}")
                    # закончили с ошибкой — busy -> False, report остаётся 'page'
                    self._pool_set(busy=False)
                    return {"found": True, "closed": closed_any, "key": page_key}
                closed_any = True
                # после закрытия страницы — новый круг
                continue

            # 2) Блокеры — после того как экран очищен от страниц
            blk = self.engine.scan_blocker(win, lang)
            if blk:
                bkey = str(blk.get("key") or "")
                self._pool_set(report="blocker")
                console.hud("ok", f"[UI_GUARD] blocker {bkey}")
                handled = bool(self.engine.handle_blocker(win, lang, bkey))
                if handled:
                    closed_any = True
                    # обработали — идём на новый круг
                    continue
                else:
                    # например, disconnect — просто уведомили
                    self._pool_set(busy=False)  # report остаётся 'blocker'
                    return {"found": True, "closed": closed_any, "key": bkey}

            # Ничего не найдено — экран чист
            if closed_any:
                console.hud("succ", "[UI_GUARD] screen clear")
            # финальный статус: busy=False, report=empty
            self._pool_set(busy=False, report="empty")
            return {
                "found": closed_any,
                "closed": closed_any,
                "key": "empty" if closed_any else ""
            }
