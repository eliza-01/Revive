# core/engines/ui_guard/server/boh/engine.py
from __future__ import annotations
import time
from typing import Optional, Dict, Tuple, Any

from core.vision.zones import compute_zone_ltrb
from core.vision.matching.template_matcher_2 import match_key_in_zone_single

from .ui_guard_data import (
    ZONES,
    PAGES_BLOCKER,
    PAGES_CLOSE_BUTTONS,
    DASHBOARD_BLOCKER,
    LANGUAGE_BLOCKER,
    DISCONNECT_BLOCKER,
)

from core.logging import console
from core.state.pool import pool_get, pool_write


Point = Tuple[int, int]
Zone = Tuple[int, int, int, int]

DEFAULT_CLICK_THRESHOLD = 0.85
DEFAULT_CONFIRM_TIMEOUT_S = 3.0


class UIGuardEngine:
    """
    Движок «стража UI»:
      - Обособленные проверки: pages_blocker, dashboard_blocker, language_blocker, disconnect_blocker
      - Поиск шаблонов — как в dashboard/buffer: match_key_in_zone_single (без своих cv2-циклов)
      - Клик — явный через контроллер, затем перепроверка исчезновения
    """

    def __init__(
        self,
        server: str,
        controller: Any,
        *,
        state: Optional[Dict[str, Any]] = None,
        click_threshold: float = DEFAULT_CLICK_THRESHOLD,
        confirm_timeout_s: float = DEFAULT_CONFIRM_TIMEOUT_S,
    ):
        self.server = (server or "boh").lower()
        self.controller = controller
        self.s = state
        self.click_threshold = float(click_threshold)
        self.confirm_timeout_s = float(confirm_timeout_s)

    # --- helpers -----------------------------------------------------------

    @staticmethod
    def _zone_ltrb(window: Dict, name: str = "fullscreen") -> Zone:
        decl = ZONES.get(name, {"fullscreen": True})
        l, t, r, b = compute_zone_ltrb(window, decl)
        return int(l), int(t), int(r), int(b)

    def _click(self, x: int, y: int, *, hover_delay_s: float = 0.20, post_delay_s: float = 0.20) -> None:
        try:
            if hasattr(self.controller, "move"):
                self.controller.move(int(x), int(y))
            time.sleep(max(0.0, float(hover_delay_s)))
            if hasattr(self.controller, "_click_left_arduino"):
                self.controller._click_left_arduino()
            else:
                self.controller.send("l")
            time.sleep(max(0.0, float(post_delay_s)))
        except Exception:
            pass

    def _toggle_layout(self, *, count: int = 1, delay_ms: int = 120) -> None:
        """Alt+Shift переключение раскладки (оставлено для совместимости)."""
        for _ in range(max(1, int(count))):
            try:
                self.controller.send("layout_toggle_altshift")
            except Exception:
                pass
            if delay_ms > 0:
                time.sleep(delay_ms / 1000.0)

    @staticmethod
    def _parts(group: str, filename: str) -> Tuple[str, ...]:
        # Все шаблоны лежат под templates/<lang>/interface/<group>/<filename>
        return ("<lang>", "interface", group, filename)

    def _match(self, window: Dict, lang: str, parts: Tuple[str, ...], thr: float) -> Optional[Point]:
        pt = match_key_in_zone_single(
            window=window,
            zone_ltrb=self._zone_ltrb(window, "fullscreen"),
            server=self.server,
            lang=(lang or "rus").lower(),
            template_parts=list(parts),
            threshold=float(thr),
            engine="ui_guard",
        )
        return pt

    # ====== pages_blocker ======
    def detect_pages_blocker(self, window: Dict, lang: str) -> bool:
        for fname in (PAGES_BLOCKER or {}).values():
            parts = self._parts("pages", fname)
            pt = self._match(window, lang, parts, self.click_threshold)
            if pt:
                return True
        return False

    def close_all_pages_crosses(self, window: Dict, lang: str) -> bool:
        """
        Прожать кнопку(и) закрытия из PAGES_CLOSE_BUTTONS, пока доступны (match→click),
        с мягким таймаутом подтверждения.
        """
        if not PAGES_CLOSE_BUTTONS:
            return False

        btn_fname = PAGES_CLOSE_BUTTONS.get("pages_close_button", "")
        if not btn_fname:
            return False
        parts = self._parts("buttons", btn_fname)

        clicked_any = False
        deadline = time.time() + self.confirm_timeout_s
        while time.time() < deadline:
            pt = self._match(window, lang, parts, self.click_threshold)
            if not pt:
                # нет кнопки — значит закрыли всё, что могли
                break
            clicked_any = True
            self._click(pt[0], pt[1], hover_delay_s=0.15, post_delay_s=0.15)
            time.sleep(0.10)

        return clicked_any

    # ====== dashboard_blocker ======
    def detect_dashboard_blocker(self, window: Dict, lang: str) -> bool:
        fname = DASHBOARD_BLOCKER.get("dashboard_blocker", "")
        if not fname:
            return False
        parts = self._parts("dashboard", fname)
        return self._match(window, lang, parts, self.click_threshold) is not None

    def close_dashboard_blocker(self, window: Dict, lang: str) -> bool:
        fname = DASHBOARD_BLOCKER.get("dashboard_blocker_close_button", "")
        if not fname:
            return False
        parts_close = self._parts("dashboard", fname)

        clicked_any = False
        deadline = time.time() + self.confirm_timeout_s
        while time.time() < deadline:
            pt = self._match(window, lang, parts_close, self.click_threshold)
            if pt:
                clicked_any = True
                self._click(pt[0], pt[1], hover_delay_s=0.15, post_delay_s=0.15)
                time.sleep(0.12)
            # проверяем исчезновение блокера
            if not self.detect_dashboard_blocker(window, lang):
                return True
            time.sleep(0.05)

        return not self.detect_dashboard_blocker(window, lang)

    # ====== language_blocker ======
    def detect_language_blocker(self, window: Dict, lang: str) -> bool:
        fname = LANGUAGE_BLOCKER.get("language_blocker", "")
        if not fname:
            return False
        parts = self._parts("wrong_word", fname)
        return self._match(window, lang, parts, self.click_threshold) is not None

    def handle_language_blocker(self, window: Dict, lang: str) -> bool:
        btn_fname = LANGUAGE_BLOCKER.get("language_blocker_close_button", "")
        if not btn_fname:
            return False
        parts_close = self._parts("wrong_word", btn_fname)

        # (оставлено как было) — переключить раскладку один раз
        self._toggle_layout(count=1, delay_ms=120)

        clicked_any = False
        deadline = time.time() + self.confirm_timeout_s
        while time.time() < deadline:
            pt = self._match(window, lang, parts_close, self.click_threshold)
            if pt:
                clicked_any = True
                self._click(pt[0], pt[1], hover_delay_s=0.15, post_delay_s=0.15)
                time.sleep(0.12)
            # исчез ли блокер?
            if not self.detect_language_blocker(window, lang):
                return True
            time.sleep(0.05)

        return not self.detect_language_blocker(window, lang)

    # ====== disconnect_blocker ======
    def detect_disconnect_blocker(self, window: Dict, lang: str) -> bool:
        fname = DISCONNECT_BLOCKER.get("disconnect_blocker", "")
        if not fname:
            return False
        parts = self._parts("disconnect", fname)
        return self._match(window, lang, parts, self.click_threshold) is not None

    def handle_disconnect_blocker(self, window: Dict, lang: str) -> bool:
        """
        Заглушка: только уведомление.
        """
        console.hud("att", "Обнаружен disconnect_blocker")
        return False  # не закрываем

    # --- UNSTUCK: без изменений ------------------------------------------
    def run_unstuck(self) -> None:
        console.hud("ok", "[UNSTUCK] Отправляю /unstuck")
        try:
            if hasattr(self.controller, "send"):
                # зачищаем чат
                self.controller.send("press_enter")
                for _ in range(20):
                    self.controller.send("backspace_click")
                    time.sleep(0.05)

                time.sleep(0.06)
                self.controller.send("enter_text /unstuck")
                time.sleep(0.06)
                self.controller.send("press_enter")
        except Exception as e:
            console.log(f"[UNSTUCK] chat send error: {e}")

        console.hud("ok", "[UNSTUCK] Ожидание 25 секунд…") #убрать хардкод
        time.sleep(25.0)

        if not isinstance(getattr(self, "s", None), dict):
            console.hud("succ", "[UNSTUCK] Готово")
            return

        try:
            keep = {
                "respawn": bool(pool_get(self.s, "features.respawn.enabled", False)),
                "buff": bool(pool_get(self.s, "features.buff.enabled", False)),
                "macros": bool(pool_get(self.s, "features.macros.enabled", False)),
                "teleport": bool(pool_get(self.s, "features.teleport.enabled", False)),
                "record": bool(pool_get(self.s, "features.record.enabled", False)),
                "autofarm": bool(pool_get(self.s, "features.autofarm.enabled", False)),
                "autofarm_cfg": pool_get(self.s, "features.autofarm.config", {}),
            }

            for node in ("respawn", "buff", "macros", "teleport", "record", "autofarm", "stabilize"):
                pool_write(self.s, f"features.{node}", {"status": "idle", "busy": False, "waiting": False})
            pool_write(self.s, "features.ui_guard", {"busy": False, "report": "empty"})
            pool_write(self.s, "features.buff", {"attempts": 0})
            pool_write(self.s, "features.teleport", {"attempts": 0})

            for k in ("respawn", "buff", "macros", "teleport", "record", "autofarm"):
                pool_write(self.s, f"features.{k}", {"enabled": keep[k]})
            pool_write(self.s, "features.autofarm", {"config": keep["autofarm_cfg"]})

            pool_write(self.s, "player", {"alive": None, "hp_ratio": None, "cp_ratio": None})
        except Exception as e:
            console.log(f"[UNSTUCK] pool reset error: {e}")

        console.hud("succ", "[UNSTUCK] Готово")

    def api_unstuck(self):
        try:
            self.run_unstuck()
            return True
        except Exception as e:
            console.log(f"[UNSTUCK] api error: {e}")
            return False
