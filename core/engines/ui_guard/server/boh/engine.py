from __future__ import annotations
import time
from typing import Optional, Dict, Tuple, Any, List

import cv2

from core.vision.zones import compute_zone_ltrb
from core.vision.matching.template_matcher import match_in_zone
from core.vision.capture.window_bgr_capture import capture_window_region_bgr

from .templates import resolver as tplresolver
from .ui_guard_data import ZONES, PAGES, CLOSE_BUTTONS

Point = Tuple[int, int]
Zone = Tuple[int, int, int, int]

DEFAULT_CLICK_THRESHOLD = 0.75   # чуть мягче, чем 0.70
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
        Пройтись по известным страницам и вернуть {"key": str, "pt": (x,y)} первой найденной.
        """
        zone_decl = ZONES.get("fullscreen")
        if not zone_decl or not window:
            return None
        ltrb = compute_zone_ltrb(window, zone_decl)

        # 1) основной путь — через match_in_zone
        for key, fname in PAGES.items():
            pt = self._match(window, lang, ["<lang>", "interface", "pages", fname], ltrb)
            if pt is not None:
                if self.debug:
                    self._log(f"[ui_guard] page={key} via matcher @ {pt}")
                return {"key": key, "pt": pt}

        # 2) fallback — чистый OpenCV со скейлами
        fb = self._fallback_scan_pages(window, (lang or "rus").lower(), ltrb)
        if fb is not None:
            (pt, key, score) = fb
            if self.debug:
                self._log(f"[ui_guard/fallback] page={key} score={score:.3f} @ {pt}")
            return {"key": key, "pt": pt}

        return None

    def try_close(self, window: Dict, lang: str, page_key: str) -> bool:
        btn_name = CLOSE_BUTTONS["dashboard"] if page_key == "dashboard_page" else CLOSE_BUTTONS["default"]
        zone_decl = ZONES.get("fullscreen")
        ltrb = compute_zone_ltrb(window, zone_decl)

        # 1) match_in_zone
        btn_pt = self._match(window, lang, ["<lang>", "interface", "buttons", btn_name], ltrb)
        if btn_pt is None:
            # 2) fallback
            fb = self._fallback_match(window, (lang or "rus").lower(), ["<lang>", "interface", "buttons", btn_name], ltrb)
            if fb is not None:
                btn_pt = fb[0]

        if btn_pt is None:
            self._report(f"[UI_GUARD] close button not found for {page_key}")
            return False

        self._report(f"[UI_GUARD] click close @ {btn_pt[0]},{btn_pt[1]} ({page_key})")
        self._click(btn_pt[0], btn_pt[1])

        # ждём исчезновения страницы
        deadline = time.time() + self.confirm_timeout_s
        while time.time() < deadline:
            if self.scan_open_page(window, lang) is None:
                self._report("[UI_GUARD] overlay closed")
                return True
            time.sleep(0.05)

        self._report("[UI_GUARD] overlay still visible (timeout)")
        return False

    # --- internals ---
    def _match(self, window: Dict, lang: str, parts: List[str], ltrb: Zone) -> Optional[Point]:
        pt = match_in_zone(
            window=window,
            zone_ltrb=ltrb,
            server=self.server,
            lang=(lang or "rus").lower(),
            template_parts=parts,
            threshold=self.click_threshold,
            engine="ui_guard",
        )
        if pt is not None and self.debug:
            self._log(f"[ui_guard] match: {'/'.join(parts)} @ {pt}")
        return pt

    def _fallback_scan_pages(self, window: Dict, lang: str, ltrb: Zone) -> Optional[Tuple[Point, str, float]]:
        """
        Перебираем все PAGES и ищем лучший матч по cv2.matchTemplate с несколькими масштабами.
        Возвращаем ((x, y), key, score) для наилучшего ≥ threshold.
        """
        img = capture_window_region_bgr(window, ltrb)
        if img is None or img.size == 0:
            return None

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        best = None  # {'score': float, 'loc': (x,y), 'w': int, 'h': int, 'key': str}

        scales = (1.0, 0.9, 1.1, 0.8, 1.2)
        for key, fname in PAGES.items():
            path = tplresolver.resolve(lang, "<lang>", "interface", "pages", fname)
            if not path:
                if self.debug:
                    self._log(f"[ui_guard/fallback] template not resolved: {key}/{fname}")
                continue

            tpl = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
            if tpl is None or tpl.size == 0:
                if self.debug:
                    self._log(f"[ui_guard/fallback] failed to read: {path}")
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

    def _fallback_match(self, window: Dict, lang: str, parts: List[str], ltrb: Zone) -> Optional[Tuple[Point, float]]:
        """
        Fallback-матч для одиночного шаблона (кнопки закрытия).
        """
        img = capture_window_region_bgr(window, ltrb)
        if img is None or img.size == 0:
            return None

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        path = tplresolver.resolve(lang, *parts)
        if not path:
            return None

        tpl = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
        if tpl is None or tpl.size == 0:
            return None

        best = None
        scales = (1.0, 0.9, 1.1, 0.8, 1.2)
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
                best = {'score': score, 'loc': maxLoc, 'w': t.shape[1], 'h': t.shape[0]}

        if best and best['score'] >= self.click_threshold:
            zl, zt, _, _ = ltrb
            cx_client = zl + best['loc'][0] + best['w'] // 2
            cy_client = zt + best['loc'][1] + best['h'] // 2
            win_x = int(window.get("x", 0))
            win_y = int(window.get("y", 0))
            return ((win_x + cx_client, win_y + cy_client), float(best['score']))
        return None

    def _click(self, x: int, y: int, delay_s: float = 0.20) -> None:
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
