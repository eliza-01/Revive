# core/engines/ui_guard/server/boh/engine.py
from __future__ import annotations
import time
from typing import Optional, Dict, Tuple, Any, List

import cv2
import numpy as np

from core.vision.zones import compute_zone_ltrb
from core.vision.capture.window_bgr_capture import capture_window_region_bgr

from .templates import resolver as tplresolver
from .ui_guard_data import ZONES, PAGES, CLOSE_BUTTONS

Point = Tuple[int, int]
Zone = Tuple[int, int, int, int]

DEFAULT_CLICK_THRESHOLD = 0.75
DEFAULT_CONFIRM_TIMEOUT_S = 3.0

class UIGuardEngine:
    """
    Детект «страниц» (оверлеев) и закрытие по крестику/кнопке.
    """
    def __init__(
        self,
        server: str,
        controller: Any,
        *,
        click_threshold: float = DEFAULT_CLICK_THRESHOLD,
        confirm_timeout_s: float = DEFAULT_CONFIRM_TIMEOUT_S,
        debug: bool = False,
        on_report: Optional[callable] = None,
    ):
        self.server = (server or "boh").lower()
        self.controller = controller
        self.click_threshold = float(click_threshold)
        self.confirm_timeout_s = float(confirm_timeout_s)
        self.debug = bool(debug)
        self._report = on_report or (lambda *_: None)

    # --- API ---
    def scan_open_page(self, window: Dict, lang: str) -> Optional[Dict[str, Any]]:
        """
        Возвращает {"key": str, "pt": (x,y)} первой найденной страницы, либо None.
        """
        zone_decl = ZONES.get("fullscreen")
        if not zone_decl or not window:
            return None
        ltrb = compute_zone_ltrb(window, zone_decl)

        # Быстрый проход: ищем любую из PAGES через OpenCV (масштабирование).
        fb = self._fallback_scan_pages(window, (lang or "rus").lower(), ltrb)
        if fb is not None:
            (pt, key, score) = fb
            if self.debug:
                self._log(f"[ui_guard] page={key} score={score:.3f} @ {pt}")
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
            # кликаем уникальные точки (дедуп уже сделан внутри)
            for (x, y) in points:
                self._report(f"[UI_GUARD] click close {page_key} @ {x},{y}")
                self._click(x, y)
                time.sleep(0.06)  # короткая стабилизация между кликами
            time.sleep(0.12)  # стабилизация кадра перед новой волной

            # safety: чтобы не попасть в бесконечный цикл на шуме
            if waves >= 10:
                self._log(f"[ui_guard] too many waves for {page_key} -> break")
                break

        # 2) подтверждаем, что именно эта страница исчезла
        deadline = time.time() + self.confirm_timeout_s
        while time.time() < deadline:
            cur = self.scan_open_page(window, lang)
            if cur is None or cur.get("key") != page_key:
                return True
            time.sleep(0.05)

        self._log(f"[ui_guard] timeout closing {page_key}")
        return False

    # --- internals ---
    def _fallback_scan_pages(self, window: Dict, lang: str, ltrb: Zone) -> Optional[Tuple[Point, str, float]]:
        """
        Ищем лучшую страницу по cv2.matchTemplate на нескольких масштабах.
        """
        img = capture_window_region_bgr(window, ltrb)
        if img is None or img.size == 0:
            return None

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        best = None
        scales = (1.0, 0.9, 1.1, 0.8, 1.2)
        for key, fname in PAGES.items():
            path = tplresolver.resolve(lang, "<lang>", "interface", "pages", fname)
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
        Находит ВСЕ совпадения шаблона (кнопки закрытия) с порогом, на нескольких масштабах.
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

        # Чтобы не уехало в бесконечный спам — адекватный набор масштабов
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

            # итеративно снимаем максимумы, затирая окрестность
            while True:
                minVal, maxVal, minLoc, maxLoc = cv2.minMaxLoc(res)
                if float(maxVal) < self.click_threshold:
                    break
                x0, y0 = maxLoc
                # центр в координатах ЗОНЫ
                cx_zone = x0 + t.shape[1] // 2
                cy_zone = y0 + t.shape[0] // 2
                # в экранные координаты
                zl, zt, _, _ = ltrb
                win_x = int(window.get("x", 0))
                win_y = int(window.get("y", 0))
                cx_screen = win_x + zl + cx_zone
                cy_screen = win_y + zt + cy_zone
                raw_points.append((int(cx_screen), int(cy_screen)))

                # подавляем окрестность найденного (NMS)
                rx = max(0, x0 - t.shape[1] // 2)
                ry = max(0, y0 - t.shape[0] // 2)
                rx2 = min(res_w, x0 + t.shape[1] // 2)
                ry2 = min(res_h, y0 + t.shape[0] // 2)
                res[ry:ry2, rx:rx2] = -1.0

        # дедуп по близости (если разные масштабы дали почти одно и то же)
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
                self.controller._click_left_arduino()
            else:
                self.controller.send("l")
        except Exception:
            pass

    def _log(self, msg: str):
        if self.debug:
            try:
                print(msg)
            except Exception:
                pass

def create_engine(**kw):
    return UIGuardEngine(**kw)
