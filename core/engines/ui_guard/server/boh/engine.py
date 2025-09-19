from __future__ import annotations
import time
from typing import Optional, Dict, Tuple, Any, List

import cv2

from core.vision.zones import compute_zone_ltrb
from core.vision.capture.window_bgr_capture import capture_window_region_bgr

from .templates import resolver as tplresolver
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

DEFAULT_CLICK_THRESHOLD = 0.75
DEFAULT_CONFIRM_TIMEOUT_S = 3.0


class UIGuardEngine:
    """
    Движок «стража UI» под новые ui_guard_data:
      - Обособленные проверки: pages_blocker, dashboard_blocker, language_blocker, disconnect_blocker
      - Каждая проверка доступна по отдельности (методы detect_* / close_* / handle_*)
      - Общие утилиты поиска/клика по шаблонам
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

    # --- debug gating ---
    def _dbg_enabled(self) -> bool:
        try:
            return pool_get(None, "runtime.debug.ui_guard_debug", False) is True
        except Exception:
            return False

    def _dbg(self, msg: str):
        try:
            if self._dbg_enabled():
                console.log(f"[UI_GUARD/DBG] {msg}")
        except Exception:
            pass

    # --- helpers ---
    @staticmethod
    def _zone_ltrb(window: Dict, name: str = "fullscreen") -> Zone:
        decl = ZONES.get(name, {"fullscreen": True})
        l, t, r, b = compute_zone_ltrb(window, decl)
        return int(l), int(t), int(r), int(b)

    def _click(self, x: int, y: int, delay_s: float = 0.15) -> None:
        try:
            if hasattr(self.controller, "move"):
                self.controller.move(int(x), int(y))
            time.sleep(max(0.0, float(delay_s)))
            if hasattr(self.controller, "_click_left_arduino"):
                self._dbg(f"click arduino @ {x},{y}")
                self.controller._click_left_arduino()
            else:
                self._dbg(f"click send(l) @ {x},{y}")
                self.controller.send("l")
        except Exception:
            pass

    def _toggle_layout(self, *, count: int = 1, delay_ms: int = 120) -> None:
        """Alt+Shift переключение раскладки."""
        for _ in range(max(1, int(count))):
            try:
                self.controller.send("layout_toggle_altshift")
            except Exception:
                pass
            if delay_ms > 0:
                time.sleep(delay_ms / 1000.0)

    # --- generic template scan ---
    def _scan_mapping_best(
        self,
        window: Dict,
        lang: str,
        ltrb: Zone,
        mapping: Dict[str, str],
        *,
        subdir: Tuple[str, ...],
    ) -> Optional[Tuple[Point, str, float]]:
        """
        Универсальный сканер по словарю {key: filename} в указанной подпапке.
        Возвращает ((x,y), key, score) лучшего совпадения при score >= threshold.
        """
        img = capture_window_region_bgr(window, ltrb)
        if img is None or img.size == 0:
            return None

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        best = None
        scales = (1.0, 0.9, 1.1, 0.8, 1.2)
        for key, fname in mapping.items():
            path = tplresolver.resolve((lang or "rus").lower(), "<lang>", *subdir, fname)
            if not path:
                continue

            tpl = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
            if tpl is None or tpl.size == 0:
                continue

            for s in scales:
                tw = max(1, int(round(tpl.shape[1] * s)))
                th = max(1, int(round(tpl.shape[0] * s)))
                t = cv2.resize(tpl, (tw, th), interpolation=cv2.INTER_AREA if s < 1.0 else cv2.INTER_CUBIC)
                if t.shape[0] > gray.shape[0] or t.shape[1] > gray.shape[1]:
                    continue

                res = cv2.matchTemplate(gray, t, cv2.TM_CCOEFF_NORMED)
                _, maxVal, _, maxLoc = cv2.minMaxLoc(res)
                score = float(maxVal)
                if best is None or score > best["score"]:
                    best = {"score": score, "loc": maxLoc, "w": t.shape[1], "h": t.shape[0], "key": key}

        if best and best["score"] >= self.click_threshold:
            zl, zt, _, _ = ltrb
            cx_client = zl + best["loc"][0] + best["w"] // 2
            cy_client = zt + best["loc"][1] + best["h"] // 2
            win_x = int(window.get("x", 0))
            win_y = int(window.get("y", 0))
            return ((win_x + cx_client, win_y + cy_client), best["key"], float(best["score"]))
        return None

    def _find_all_buttons(self, window: Dict, lang: str, filename: str, ltrb: Zone) -> List[Point]:
        """
        Находит ВСЕ совпадения шаблона кнопки (по filename) на нескольких масштабах.
        Возвращает список экранных координат центров кнопок (дедуплицированный).
        """
        img = capture_window_region_bgr(window, ltrb)
        if img is None or img.size == 0:
            return []
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        path = tplresolver.resolve((lang or "rus").lower(), "<lang>", "interface", "buttons", filename)
        if not path:
            return []

        tpl0 = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
        if tpl0 is None or tpl0.size == 0:
            return []

        scales = (1.0, 0.95, 1.05, 0.90, 1.10)
        raw_points: List[Tuple[int, int]] = []

        for s in scales:
            tw = max(1, int(round(tpl0.shape[1] * s)))
            th = max(1, int(round(tpl0.shape[0] * s)))
            t = cv2.resize(tpl0, (tw, th), interpolation=cv2.INTER_AREA if s < 1.0 else cv2.INTER_CUBIC)
            if t.shape[0] > gray.shape[0] or t.shape[1] > gray.shape[1]:
                continue

            res = cv2.matchTemplate(gray, t, cv2.TM_CCOEFF_NORMED)
            res_h, res_w = res.shape[:2]

            while True:
                _, maxVal, _, maxLoc = cv2.minMaxLoc(res)
                if float(maxVal) < self.click_threshold:
                    break
                x0, y0 = maxLoc
                cx_zone = x0 + t.shape[1] // 2
                cy_zone = y0 + t.shape[0] // 2
                zl, zt, _, _ = ltrb
                win_x = int(window.get("x", 0))
                win_y = int(window.get("y", 0))
                cx_screen = win_x + zl + cx_zone
                cy_screen = win_y + zt + cy_zone
                raw_points.append((int(cx_screen), int(cy_screen)))

                # подавление окрестности
                rx = max(0, x0 - t.shape[1] // 2)
                ry = max(0, y0 - t.shape[0] // 2)
                rx2 = min(res_w, x0 + t.shape[1] // 2)
                ry2 = min(res_h, y0 + t.shape[0] // 2)
                res[ry:ry2, rx:rx2] = -1.0

        return self._dedup_points(raw_points, radius=12)

    @staticmethod
    def _dedup_points(pts: List[Point], radius: int = 10) -> List[Point]:
        out: List[Point] = []
        r2 = radius * radius
        for p in pts:
            if not any((p[0]-q[0])**2 + (p[1]-q[1])**2 <= r2 for q in out):
                out.append(p)
        return out

    # ====== pages_blocker ======
    def detect_pages_blocker(self, window: Dict, lang: str) -> bool:
        ltrb = self._zone_ltrb(window, "fullscreen")
        hit = self._scan_mapping_best(window, lang, ltrb, PAGES_BLOCKER, subdir=("interface", "pages"))
        return hit is not None

    def close_all_pages_crosses(self, window: Dict, lang: str) -> bool:
        """
        Прожать ВСЕ кнопки из PAGES_CLOSE_BUTTONS «волнами», пока они не закончатся.
        Возвращает True, если что-то кликнули.
        """
        if not PAGES_CLOSE_BUTTONS:
            return False
        ltrb = self._zone_ltrb(window, "fullscreen")

        clicked_any = False
        for wave in range(1, 16):
            pts: List[Point] = []
            for _, fname in (PAGES_CLOSE_BUTTONS or {}).items():
                pts += self._find_all_buttons(window, lang, fname, ltrb)
            pts = self._dedup_points(pts, radius=12)

            if not pts:
                # пусто — завершаем
                break

            clicked_any = True
            console.log(f"[UI_GUARD] pages_close wave {wave}: {len(pts)} clicks")
            for (x, y) in pts:
                self._click(x, y)
                time.sleep(0.05)
            time.sleep(0.12)

        return clicked_any

    # ====== dashboard_blocker ======
    def detect_dashboard_blocker(self, window: Dict, lang: str) -> bool:
        ltrb = self._zone_ltrb(window, "fullscreen")
        mapping = {"dashboard_blocker": DASHBOARD_BLOCKER.get("dashboard_blocker", "")}
        hit = self._scan_mapping_best(window, lang, ltrb, mapping, subdir=("interface", "blockers"))
        return hit is not None

    def close_dashboard_blocker(self, window: Dict, lang: str) -> bool:
        """
        Нажать кнопки dashboard_blocker_close_button до исчезновения dashboard_blocker.
        """
        ltrb = self._zone_ltrb(window, "fullscreen")
        btn_fname = DASHBOARD_BLOCKER.get("dashboard_blocker_close_button", "")
        if not btn_fname:
            return False

        clicked_any = False
        deadline = time.time() + self.confirm_timeout_s
        while time.time() < deadline:
            pts = self._find_all_buttons(window, lang, btn_fname, ltrb)
            pts = self._dedup_points(pts, radius=12)
            if not pts:
                # проверим, исчез ли сам блокер
                if not self.detect_dashboard_blocker(window, lang):
                    return clicked_any
                time.sleep(0.08)
                continue

            clicked_any = True
            for (x, y) in pts:
                self._click(x, y)
                time.sleep(0.06)
            time.sleep(0.12)

            if not self.detect_dashboard_blocker(window, lang):
                return True

        return not self.detect_dashboard_blocker(window, lang)

    # ====== language_blocker ======
    def detect_language_blocker(self, window: Dict, lang: str) -> bool:
        ltrb = self._zone_ltrb(window, "fullscreen")
        mapping = {"language_blocker": LANGUAGE_BLOCKER.get("language_blocker", "")}
        hit = self._scan_mapping_best(window, lang, ltrb, mapping, subdir=("interface", "blockers"))
        return hit is not None

    def handle_language_blocker(self, window: Dict, lang: str) -> bool:
        """
        Поменять раскладку → нажать language_blocker_close_button → убедиться, что блокер исчез.
        """
        ltrb = self._zone_ltrb(window, "fullscreen")
        btn_fname = LANGUAGE_BLOCKER.get("language_blocker_close_button", "")
        if not btn_fname:
            return False

        # переключить раскладку (Alt+Shift)
        self._toggle_layout(count=1, delay_ms=120)

        clicked_any = False
        deadline = time.time() + self.confirm_timeout_s
        while time.time() < deadline:
            pts = self._find_all_buttons(window, lang, btn_fname, ltrb)
            pts = self._dedup_points(pts, radius=12)

            if pts:
                clicked_any = True
                for (x, y) in pts:
                    self._click(x, y)
                    time.sleep(0.08)
                time.sleep(0.12)

            # исчез ли блокер?
            if not self.detect_language_blocker(window, lang):
                return True

            time.sleep(0.05)

        return not self.detect_language_blocker(window, lang)

    # ====== disconnect_blocker ======
    def detect_disconnect_blocker(self, window: Dict, lang: str) -> bool:
        ltrb = self._zone_ltrb(window, "fullscreen")
        mapping = {"disconnect_blocker": DISCONNECT_BLOCKER.get("disconnect_blocker", "")}
        hit = self._scan_mapping_best(window, lang, ltrb, mapping, subdir=("interface", "blockers"))
        return hit is not None

    def handle_disconnect_blocker(self, window: Dict, lang: str) -> bool:
        """
        Заглушка: только уведомление.
        """
        console.hud("att", "Обнаружен disconnect_blocker")
        return False  # не закрываем

    # --- UNSTUCK: без изменений (аккуратно сбрасывает статусы) ---
    def run_unstuck(self) -> None:
        console.hud("ok", "[UNSTUCK] Отправляю /unstuck")
        try:
            if hasattr(self.controller, "send"):
                self.controller.send("press_enter")
                time.sleep(0.06)
                self.controller.send("enter_text /unstuck")
                time.sleep(0.06)
                self.controller.send("press_enter")
        except Exception as e:
            console.log(f"[UNSTUCK] chat send error: {e}")

        console.hud("ok", "[UNSTUCK] Ожидание 20 секунд…")
        time.sleep(20.0)

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
