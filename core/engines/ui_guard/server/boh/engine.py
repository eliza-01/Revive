from __future__ import annotations
import time
from typing import Optional, Dict, Tuple, Any, List

import cv2
# import numpy as np

from core.vision.zones import compute_zone_ltrb
from core.vision.capture.window_bgr_capture import capture_window_region_bgr

from .templates import resolver as tplresolver
from .ui_guard_data import ZONES, PAGES, CLOSE_BUTTONS, BLOCKERS

from core.logging import console
from core.state.pool import pool_get

Point = Tuple[int, int]
Zone = Tuple[int, int, int, int]

DEFAULT_CLICK_THRESHOLD = 0.75
DEFAULT_CONFIRM_TIMEOUT_S = 3.0


class UIGuardEngine:
    """
    Детект «страниц» (оверлеев), блокеров и закрытие по крестику/кнопке.
    """

    def __init__(
        self,
        server: str,
        controller: Any,
        *,
        click_threshold: float = DEFAULT_CLICK_THRESHOLD,
        confirm_timeout_s: float = DEFAULT_CONFIRM_TIMEOUT_S,
    ):
        self.server = (server or "boh").lower()
        self.controller = controller
        self.click_threshold = float(click_threshold)
        self.confirm_timeout_s = float(confirm_timeout_s)

    # --- debug gating ---
    def _dbg_enabled(self) -> bool:
        try:
            # включаем только при явном True
            return pool_get(None, "runtime.debug.ui_guard_debug", False) is True
        except Exception:
            return False

    def _dbg(self, msg: str):
        try:
            if self._dbg_enabled():
                console.log(f"[UI_GUARD/DBG] {msg}")
        except Exception:
            pass

    # --- API: страницы ---
    def scan_open_page(self, window: Dict, lang: str) -> Optional[Dict[str, Any]]:
        """
        Возвращает {"key": str, "pt": (x,y)} первой найденной страницы, либо None.
        """
        zone_decl = ZONES.get("fullscreen")
        if not zone_decl or not window:
            return None
        ltrb = compute_zone_ltrb(window, zone_decl)

        fb = self._fallback_scan_mapping(
            window, (lang or "rus").lower(), ltrb, PAGES, subdir=("interface", "pages")
        )
        if fb is not None:
            (pt, key, score) = fb
            self._dbg(f"page={key} score={score:.3f} @ {pt}")
            return {"key": key, "pt": pt}
        return None

    def try_close(self, window: Dict, lang: str, page_key: str) -> bool:
        """
        Жмём ВСЕ кресты этой страницы, пока они находятся. Затем подтверждаем исчезновение этой же страницы.
        """
        btn_name = CLOSE_BUTTONS["dashboard_close_button"] if page_key == "dashboard_page" else CLOSE_BUTTONS["default_close_button"]
        ltrb = compute_zone_ltrb(window, ZONES.get("fullscreen"))

        # 1) жмём все найденные крестики, и делаем это до «чистого» экрана от крестов
        waves = 0
        while True:
            points = self._find_all_buttons(window, lang, ["<lang>", "interface", "buttons", btn_name], ltrb)
            if not points:
                break
            waves += 1
            for (x, y) in points:
                console.log(f"[UI_GUARD] click close {page_key} @ {x},{y}")
                self._click(x, y)
                time.sleep(0.06)
            time.sleep(0.12)

            if waves >= 10:
                self._dbg(f"too many waves for {page_key} -> break")
                break

        # 2) подтверждаем, что именно эта страница исчезла
        deadline = time.time() + self.confirm_timeout_s
        while time.time() < deadline:
            cur = self.scan_open_page(window, lang)
            if cur is None or cur.get("key") != page_key:
                return True
            time.sleep(0.05)

        console.log(f"[UI_GUARD] timeout closing {page_key}")
        return False

    # --- API: блокеры ---
    def scan_blocker(self, window: Dict, lang: str) -> Optional[Dict[str, Any]]:
        """
        Возвращает {"key": str, "pt": (x,y)} первого найденного блокера, либо None.
        """
        zone_decl = ZONES.get("fullscreen")
        if not zone_decl or not window:
            return None
        ltrb = compute_zone_ltrb(window, zone_decl)

        fb = self._fallback_scan_mapping(
            window, (lang or "rus").lower(), ltrb, BLOCKERS, subdir=("interface", "blockers")
        )
        if fb is not None:
            (pt, key, score) = fb
            self._dbg(f"blocker={key} score={score:.3f} @ {pt}")
            return {"key": key, "pt": pt}
        return None

    def handle_blocker(self, window: Dict, lang: str, blocker_key: str) -> bool:
        """
        Обрабатывает обнаруженный блокер.
        Возвращает True, если блокер устранён (исчез), False — если не устранён.
        - wrong_word_popup: Alt+Shift (переключить раскладку) → нажать wrong_word_accept_button → убедиться, что попап исчез.
        - disconnect_popup: только HUD-уведомление, возвращаем False (не закрываем).
        """
        ltrb = compute_zone_ltrb(window, ZONES.get("fullscreen"))

        if blocker_key == "wrong_word_popup":
            # 1) Переключаем раскладку (Alt+Shift)
            self._toggle_layout(count=1, delay_ms=120)

            # 2) Ищем и жмём кнопку подтверждения
            btn_name = CLOSE_BUTTONS.get("wrong_word_accept_button")
            if not btn_name:
                self._dbg("wrong_word_accept_button not found in CLOSE_BUTTONS map")
                return False

            points = self._find_all_buttons(window, lang, ["<lang>", "interface", "buttons", btn_name], ltrb)
            if not points:
                self._dbg("wrong_word_accept_button: no matches")
            for (x, y) in points:
                console.log(f"[UI_GUARD] wrong_word: click accept @ {x},{y}")
                self._click(x, y)
                time.sleep(0.08)

            # 3) Дождаться исчезновения блокера
            deadline = time.time() + self.confirm_timeout_s
            while time.time() < deadline:
                cur = self.scan_blocker(window, lang)
                if cur is None or cur.get("key") != "wrong_word_popup":
                    return True
                time.sleep(0.05)
            self._dbg("wrong_word_popup still visible after timeout")
            return False

        if blocker_key == "disconnect_popup":
            console.hud("att", "Дисконнект")
            # Ничего не закрываем (по задаче) → не считаем устранённым
            return False

        # неизвестный блокер — пока ничего не делаем
        self._dbg(f"unknown blocker: {blocker_key}")
        return False

    # --- internals (generic template scan) ---
    def _fallback_scan_mapping(
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
            path = tplresolver.resolve(lang, "<lang>", *subdir, fname)
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
                if best is None or score > best['score']:
                    best = {'score': score, 'loc': maxLoc, 'w': t.shape[1], 'h': t.shape[0], 'key': key}

        if best and best['score'] >= self.click_threshold:
            zl, zt, _, _ = ltrb
            cx_client = zl + best['loc'][0] + best['w'] // 2
            cy_client = zt + best['loc'][1] + best['h'] // 2
            win_x = int(window.get("x", 0))
            win_y = int(window.get("y", 0))
            return ((win_x + cx_client, win_y + cy_client), best['key'], float(best['score']))
        return None

    def _find_all_buttons(self, window: Dict, lang: str, parts: List[str], ltrb: Zone) -> List[Point]:
        """
        Находит ВСЕ совпадения шаблона (кнопки) с порогом, на нескольких масштабах.
        Возвращает список экранных координат центров кнопок, дедуплицированный.
        """
        img = capture_window_region_bgr(window, ltrb)
        if img is None or img.size == 0:
            return []
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        path = tplresolver.resolve((lang or "rus").lower(), *parts)
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

