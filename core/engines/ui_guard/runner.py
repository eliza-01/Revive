from __future__ import annotations
from typing import Callable, Optional, Dict, Any
import time

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

    # ---- main ------------------------------------------------------------
    def run_once(self) -> Dict[str, Any]:
        # старт: просто объявляемся busy, без выставления paused
        self._pool_set(busy=True, report="empty", pause_reason="")

        # если фокуса нет — пропуск (пусть координатор рулит cor_1/cor_3)
        try:
            if not self._is_focused():
                console.hud("err", "[UI_GUARD] skip: no focus")
                # вернуть базовую причину, чтобы координатор понял контекст
                base = self._baseline_reason()
                self._pool_set(busy=False, report="empty", pause_reason=base)
                return {"found": False, "closed": False, "key": "empty", "reason": base}
        except Exception:
            base = self._baseline_reason()
            self._pool_set(busy=False, report="empty", pause_reason=base)
            return {"found": False, "closed": False, "key": "empty", "reason": base}

        win = self._get_window() or {}
        if not win:
            console.hud("err", "[UI_GUARD] no window")
            base = self._baseline_reason()
            self._pool_set(busy=False, report="empty", pause_reason=base)
            return {"found": False, "closed": False, "key": "empty", "reason": base}

        lang = (self._get_language() or "rus").lower()
        closed_any = False
        found_any = False
        current_reason = "empty"

        # ===== 1) pages_blocker =====
        self._pool_set(report="pages_blocker")
        if self.engine.detect_pages_blocker(win, lang):
            found_any = True
            current_reason = "pages_blocker"
            self._label_reason_for_paused(current_reason)
            clicked = bool(self.engine.close_all_pages_crosses(win, lang))
            closed_any = closed_any or clicked
            if self.engine.detect_pages_blocker(win, lang):
                # осталось что-то — выходим с этой причиной
                self._pool_set(busy=False, report="pages_blocker", pause_reason=current_reason)
                return {"found": True, "closed": closed_any, "key": "pages_blocker", "reason": current_reason}
            else:
                console.hud("att", "Обнаружен pages_blocker")

        # ===== 2) dashboard_blocker =====
        self._pool_set(report="dashboard_blocker")
        if self.engine.detect_dashboard_blocker(win, lang):
            found_any = True
            current_reason = "dashboard_blocker"
            self._label_reason_for_paused(current_reason)
            handled = bool(self.engine.close_dashboard_blocker(win, lang))
            if handled and (not self.engine.detect_dashboard_blocker(win, lang)):
                console.hud("att", "Обнаружен dashboard_blocker")
                closed_any = True
            else:
                self._pool_set(busy=False, report="dashboard_blocker", pause_reason=current_reason)
                return {"found": True, "closed": closed_any, "key": "dashboard_blocker", "reason": current_reason}

        # ===== 3) language_blocker =====
        self._pool_set(report="language_blocker")
        if self.engine.detect_language_blocker(win, lang):
            found_any = True
            current_reason = "language_blocker"
            self._label_reason_for_paused(current_reason)
            handled = bool(self.engine.handle_language_blocker(win, lang))
            if handled and (not self.engine.detect_language_blocker(win, lang)):
                console.hud("att", "Обнаружен language_blocker")
                closed_any = True
            else:
                self._pool_set(busy=False, report="language_blocker", pause_reason=current_reason)
                return {"found": True, "closed": closed_any, "key": "language_blocker", "reason": current_reason}

        # ===== 4) disconnect_blocker (уведомление) =====
        self._pool_set(report="disconnect_blocker")
        if self.engine.detect_disconnect_blocker(win, lang):
            found_any = True
            current_reason = "disconnect_blocker"  # для телеметрии
            console.hud("att", "Обнаружен disconnect_blocker")
            self.engine.handle_disconnect_blocker(win, lang)
            self._pool_set(busy=False, report="disconnect_blocker", pause_reason=current_reason)
            return {"found": True, "closed": closed_any, "key": "disconnect_blocker", "reason": current_reason}

        # ===== экран чист =====
        if closed_any:
            console.hud("succ", "[UI_GUARD] screen clear")

        # финал: если блокеров не нашли — оставляем базовую причину (cor_2 > cor_1),
        # чтобы координатор показал заглушку «ui_guard не нашел причину».
        base = self._baseline_reason()
        final_reason = current_reason if found_any else base
        self._pool_set(busy=False, report="empty", pause_reason=final_reason if final_reason else "empty")
        return {
            "found": bool(found_any),
            "closed": bool(closed_any),
            "key": "empty",
            "reason": final_reason if final_reason else "empty",
        }
