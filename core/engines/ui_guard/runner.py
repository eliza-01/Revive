from __future__ import annotations
from typing import Callable, Optional, Dict, Any
import time

from core.logging import console
from core.state.pool import pool_write, pool_get


class UIGuardRunner:
    """
    Общий цикл (одноразовый прогон) по блокерам:
      1) pages_blocker  → прожать все pages_close_button до исчезновения страниц
      2) dashboard_blocker → закрыть своей кнопкой
      3) language_blocker  → переключить раскладку, закрыть кнопкой
      4) disconnect_blocker → заглушка (уведомление)

    В пул пишем узел features.ui_guard:
      {
        "busy": bool,
        "paused": bool,
        "pause_reason": str,
        "report": "<pages_blocker|dashboard_blocker|language_blocker|disconnect_blocker|empty>",
        "ts": float
      }

    При обнаружении pages_blocker — ставим paused всем фичам/сервисам (кроме ui_guard).
    При последующих блокерах — обновляем pause_reason.
    В конце, если экран чист, снимаем паузы с теми, у кого pause_reason один из выше.
    """

    _REASONS = ("pages_blocker", "dashboard_blocker", "language_blocker")

    def __init__(
        self,
        engine: Any,
        get_window: Callable[[], Optional[Dict[str, Any]]],
        get_language: Callable[[], str],
        *,
        is_focused: Optional[Callable[[], bool]] = None,  # только фокус
        state: Optional[Dict[str, Any]] = None,
    ):
        self.engine = engine
        self._get_window = get_window
        self._get_language = get_language
        self._is_focused = is_focused or (lambda: True)
        self._state = state or None

    # ---- pool helpers ----------------------------------------------------
    def _pool_set(
        self,
        *,
        busy: Optional[bool] = None,
        report: Optional[str] = None,
        paused: Optional[bool] = None,
        pause_reason: Optional[str] = None,
    ) -> None:
        if self._state is None:
            return
        data: Dict[str, Any] = {"ts": time.time()}
        if busy is not None:
            data["busy"] = bool(busy)
        if report is not None:
            data["report"] = str(report)
        if paused is not None:
            data["paused"] = bool(paused)
        if pause_reason is not None:
            data["pause_reason"] = str(pause_reason)
        try:
            pool_write(self._state, "features.ui_guard", data)
        except Exception:
            pass

    def _pause_all_except_ui_guard(self, reason: str) -> None:
        if self._state is None:
            return
        # фичи
        for fk in ("respawn", "buff", "macros", "teleport", "record", "autofarm", "stabilize"):
            try:
                pool_write(self._state, f"features.{fk}", {"paused": True, "pause_reason": reason})
            except Exception:
                pass
        # сервисы
        for sk in ("player_state", "macros_repeat", "autofarm"):
            try:
                pool_write(self._state, f"services.{sk}", {"paused": True, "pause_reason": reason})
            except Exception:
                pass
        # сам ui_guard не трогаем

    def _unpause_reasons(self, reasons: tuple[str, ...]) -> None:
        if self._state is None:
            return
        reasons_set = set(reasons)
        # фичи
        for fk in ("respawn", "buff", "macros", "teleport", "record", "autofarm", "stabilize"):
            try:
                cur_reason = str(pool_get(self._state, f"features.{fk}.pause_reason", "") or "")
                if cur_reason in reasons_set:
                    pool_write(self._state, f"features.{fk}", {"paused": False, "pause_reason": ""})
            except Exception:
                pass
        # сервисы
        for sk in ("player_state", "macros_repeat", "autofarm"):
            try:
                cur_reason = str(pool_get(self._state, f"services.{sk}.pause_reason", "") or "")
                if cur_reason in reasons_set:
                    pool_write(self._state, f"services.{sk}", {"paused": False, "pause_reason": ""})
            except Exception:
                pass

    # ---- main ------------------------------------------------------------
    def run_once(self) -> Dict[str, Any]:
        # старт
        self._pool_set(busy=True, paused=False, pause_reason="", report="empty")

        # если фокуса нет — пропуск
        try:
            if not self._is_focused():
                console.hud("err", "[UI_GUARD] skip: no focus")
                self._pool_set(busy=False, report="empty")
                return {"found": False, "closed": False, "key": ""}
        except Exception:
            self._pool_set(busy=False, report="empty")
            return {"found": False, "closed": False, "key": ""}

        win = self._get_window() or {}
        if not win:
            console.hud("err", "[UI_GUARD] no window")
            self._pool_set(busy=False, report="empty")
            return {"found": False, "closed": False, "key": ""}

        lang = (self._get_language() or "rus").lower()
        closed_any = False
        found_any = False

        # ===== 1) pages_blocker =====
        self._pool_set(report="pages_blocker")
        if self.engine.detect_pages_blocker(win, lang):
            found_any = True
            # раздать паузы
            self._pause_all_except_ui_guard("pages_blocker")
            self._pool_set(paused=True, pause_reason="pages_blocker")
            # закрывать все pages_close_button волнами
            clicked = bool(self.engine.close_all_pages_crosses(win, lang))
            closed_any = closed_any or clicked
            # повторная проверка страниц
            if self.engine.detect_pages_blocker(win, lang):
                # не удалось убрать всё — остаёмся в состоянии pages_blocker
                self._pool_set(busy=False, report="pages_blocker")
                return {"found": True, "closed": closed_any, "key": "pages_blocker"}
            else:
                console.hud("att", "Обнаружен pages_blocker")
                # продолжаем к следующему шагу

        # ===== 2) dashboard_blocker =====
        self._pool_set(report="dashboard_blocker")
        if self.engine.detect_dashboard_blocker(win, lang):
            found_any = True
            # обновить reason
            self._pause_all_except_ui_guard("dashboard_blocker")
            self._pool_set(paused=True, pause_reason="dashboard_blocker")
            handled = bool(self.engine.close_dashboard_blocker(win, lang))
            if handled and (not self.engine.detect_dashboard_blocker(win, lang)):
                console.hud("att", "Обнаружен dashboard_blocker")
                closed_any = True
            else:
                # не снялся — выходим, оставляя report
                self._pool_set(busy=False, report="dashboard_blocker")
                return {"found": True, "closed": closed_any, "key": "dashboard_blocker"}

        # ===== 3) language_blocker =====
        self._pool_set(report="language_blocker")
        if self.engine.detect_language_blocker(win, lang):
            found_any = True
            self._pause_all_except_ui_guard("language_blocker")
            self._pool_set(paused=True, pause_reason="language_blocker")
            handled = bool(self.engine.handle_language_blocker(win, lang))
            if handled and (not self.engine.detect_language_blocker(win, lang)):
                console.hud("att", "Обнаружен language_blocker")
                closed_any = True
            else:
                self._pool_set(busy=False, report="language_blocker")
                return {"found": True, "closed": closed_any, "key": "language_blocker"}

        # ===== 4) disconnect_blocker (заглушка) =====
        self._pool_set(report="disconnect_blocker")
        if self.engine.detect_disconnect_blocker(win, lang):
            found_any = True
            console.hud("att", "Обнаружен disconnect_blocker")
            # уведомили — по ТЗ не закрываем
            self.engine.handle_disconnect_blocker(win, lang)
            self._pool_set(busy=False, report="disconnect_blocker")
            return {"found": True, "closed": closed_any, "key": "disconnect_blocker"}

        # ===== экран чист =====
        if closed_any:
            console.hud("succ", "[UI_GUARD] screen clear")

        # Снимаем паузы только с наших причин
        self._unpause_reasons(self._REASONS)

        self._pool_set(busy=False, paused=False, pause_reason="", report="empty")
        return {
            "found": bool(found_any),
            "closed": bool(closed_any),
            "key": "empty" if closed_any or (not found_any) else "",
        }
