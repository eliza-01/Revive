# core/engines/ui_guard/runner.py
from __future__ import annotations
from typing import Callable, Optional, Dict, Any
import time
import threading

from core.logging import console
from core.state.pool import pool_write, pool_get


class UIGuardRunner:
    """
    Новый контракт:
      - Координатор ставит паузы всем (кроме ui_guard) пока features.ui_guard.busy=True (reason: ui_guard),
        и по паттернам cor_1 / cor_2 / cor_3.
      - ui_guard НЕ ставит/снимает паузы сам. Он только:
         * помечает pause_reason у уже приостановленных фич/сервисов (если нашёл блокер),
         * пишет свой features.ui_guard.pause_reason,
         * даёт краткий отчёт 'report'.
      - По завершению цикла busy=False. Координатор видит уход причины 'ui_guard'.
        Если pause_reason пустой — снимет паузы. Если не пустой — покажет заглушку.
    """

    _REASONS = ("pages_blocker", "dashboard_blocker", "language_blocker")

    def __init__(
        self,
        engine: Any,
        get_window: Callable[[], Optional[Dict[str, Any]]],
        get_language: Callable[[], str],
        *,
        is_focused: Optional[Callable[[], bool]] = None,
        state: Optional[Dict[str, Any]] = None,
    ):
        self.engine = engine
        self._get_window = get_window
        self._get_language = get_language
        self._is_focused = is_focused or (lambda: True)
        self._state = state or None

        # watch-loop
        self._watch_thr: Optional[threading.Thread] = None
        self._watch_stop: Optional[threading.Event] = None

    # ---- helpers: pool ---------------------------------------------------
    def _pool_set(
        self,
        *,
        busy: Optional[bool] = None,
        report: Optional[str] = None,
        pause_reason: Optional[str] = None,
    ) -> None:
        if self._state is None:
            return
        data: Dict[str, Any] = {"ts": time.time()}
        if busy is not None:
            data["busy"] = bool(busy)
        if report is not None:
            data["report"] = str(report)
        if pause_reason is not None:
            data["pause_reason"] = str(pause_reason)
        try:
            pool_write(self._state, "features.ui_guard", data)
        except Exception:
            pass

    def _label_reason_for_paused(self, reason: str) -> None:
        """
        Проставить pause_reason только тем, кто уже paused=True.
        Координатор не перетирает эти метки при причине 'ui_guard'.
        """
        if self._state is None:
            return
        features = ("respawn", "buff", "macros", "teleport", "record", "autofarm", "stabilize")
        services = ("player_state", "macros_repeat", "autofarm")
        for fk in features:
            try:
                if bool(pool_get(self._state, f"features.{fk}.paused", False)):
                    pool_write(self._state, f"features.{fk}", {"pause_reason": reason})
            except Exception:
                pass
        for sk in services:
            try:
                if bool(pool_get(self._state, f"services.{sk}.paused", False)):
                    pool_write(self._state, f"services.{sk}", {"pause_reason": reason})
            except Exception:
                pass

    def _baseline_reason(self) -> str:
        """Определить текущую «базовую» причину координатора (cor_2 > cor_1)."""
        try:
            reasons = dict(pool_get(self._state, "runtime.pauses.reasons", {}) or {})
            active = {k for k, v in reasons.items() if isinstance(v, dict) and v.get("active")}
            if "cor_2" in active:
                return "cor_2"
            if "cor_1" in active:
                return "cor_1"
        except Exception:
            pass
        # пробуем считать из любой паузной фичи
        try:
            for fk in ("autofarm", "teleport", "buff", "macros", "respawn", "record", "stabilize"):
                if bool(pool_get(self._state, f"features.{fk}.paused", False)):
                    r = str(pool_get(self._state, f"features.{fk}.pause_reason", "") or "")
                    if r in ("cor_2", "cor_1"):
                        return r
        except Exception:
            pass
        return "empty"

    # ---- main single-run -------------------------------------------------
    def run_once(self) -> Dict[str, Any]:
        # 0) Ранние выходы БЕЗ записи в пул (не дергаем busy/pause_reason)
        try:
            if not self._is_focused():
                # Координатор сам держит cor_1; ui_guard тут молчит
                return {"found": False, "closed": False, "key": "empty", "reason": "empty"}
        except Exception:
            return {"found": False, "closed": False, "key": "empty", "reason": "empty"}

        win = self._get_window() or {}
        if not win:
            # Нет окна — выходим тихо
            return {"found": False, "closed": False, "key": "empty", "reason": "empty"}

        lang = (self._get_language() or "rus").lower()

        # 1) Теперь можно объявиться busy
        self._pool_set(busy=True, report="", pause_reason="")

        closed_any = False  # что-то реально закрыли
        # found_any больше не нужен для финала — если не нашли/всё закрыли, отдаём empty

        # ===== 1) pages_blocker =====
        # self._pool_set(report="pages_blocker")
        if self.engine.detect_pages_blocker(win, lang):
            clicked = bool(self.engine.close_all_pages_crosses(win, lang))
            closed_any = closed_any or clicked

            # остался ли блокер после попытки закрытия?
            if self.engine.detect_pages_blocker(win, lang):
                reason = "pages_blocker"
                self._label_reason_for_paused(reason)
                # фиксируем итог и выходим
                self._pool_set(busy=False, report=reason, pause_reason=reason)
                return {"found": True, "closed": closed_any, "key": reason, "reason": reason}
            else:
                console.hud("succ", "pages_blocker закрыт")

        # ===== 2) dashboard_blocker =====
#         self._pool_set(report="dashboard_blocker")
        if self.engine.detect_dashboard_blocker(win, lang):
            handled = bool(self.engine.close_dashboard_blocker(win, lang))
            closed_any = closed_any or handled

            if self.engine.detect_dashboard_blocker(win, lang):
                reason = "dashboard_blocker"
                self._label_reason_for_paused(reason)
                self._pool_set(busy=False, report=reason, pause_reason=reason)
                return {"found": True, "closed": closed_any, "key": reason, "reason": reason}
            else:
                console.hud("succ", "dashboard_blocker закрыт")

        # ===== 3) language_blocker =====
#         self._pool_set(report="language_blocker")
        if self.engine.detect_language_blocker(win, lang):
            handled = bool(self.engine.handle_language_blocker(win, lang))
            closed_any = closed_any or handled

            if self.engine.detect_language_blocker(win, lang):
                reason = "language_blocker"
                self._label_reason_for_paused(reason)
                self._pool_set(busy=False, report=reason, pause_reason=reason)
                return {"found": True, "closed": closed_any, "key": reason, "reason": reason}
            else:
                console.hud("succ", "language_blocker закрыт")

        # ===== 4) disconnect_blocker (уведомление) =====
#         self._pool_set(report="disconnect_blocker")
        if self.engine.detect_disconnect_blocker(win, lang):
            reason = "disconnect_blocker"
            console.hud("att", "Обнаружен disconnect_blocker")
            self.engine.handle_disconnect_blocker(win, lang)
            self._pool_set(busy=False, report=reason, pause_reason=reason)
            return {"found": True, "closed": closed_any, "key": reason, "reason": reason}

        # ===== экран чист =====
        if closed_any:
            console.hud("succ", "[UI_GUARD] screen clear")

        # 5) Финал: ничего не нашли/всё закрыли → report пустой, причина empty
        self._pool_set(busy=False, report="", pause_reason="empty")
        return {
            "found": False,
            "closed": bool(closed_any),
            "key": "empty",
            "reason": "empty",
        }

    # ---- watch-loop ------------------------------------------------------
    def start_watch(self, poll_ms: int = 500):
        if self._watch_thr and self._watch_thr.is_alive():
            return
        self._watch_stop = threading.Event()

        def _loop():
            while self._watch_stop and (not self._watch_stop.is_set()):
                try:
                    self.run_once()
                except Exception as e:
                    try:
                        console.log(f"[UI_GUARD] watch loop error: {e}")
                    except Exception:
                        pass
                # НЕ слишком агрессивно
                if self._watch_stop and self._watch_stop.wait(poll_ms / 1000.0):
                    break

        self._watch_thr = threading.Thread(target=_loop, name="UIGuardWatch", daemon=True)
        self._watch_thr.start()

    def stop_watch(self):
        if self._watch_stop:
            self._watch_stop.set()
        if self._watch_thr:
            try:
                self._watch_thr.join(timeout=0.7)
            except Exception:
                pass
        self._watch_thr = None
        self._watch_stop = None
