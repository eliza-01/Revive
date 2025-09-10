# core/engines/ui_guard/server/boh/engine.py
from __future__ import annotations
import time
from typing import Optional, Dict, Tuple, Any

from core.vision.zones import compute_zone_ltrb
from core.vision.matching.template_matcher import match_in_zone
from core.vision.capture.window_bgr_capture import capture_window_region_bgr

from .templates import resolver as tplresolver
from .ui_guard_data import ZONES, PAGES, CLOSE_BUTTONS

Point = Tuple[int, int]
Zone = Tuple[int, int, int, int]

DEFAULT_CLICK_THRESHOLD = 0.70
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
        zone_decl = ZONES.get("fullscreen")
        if not zone_decl or not window:
            return None
        ltrb = compute_zone_ltrb(window, zone_decl)

        for key, fname in PAGES.items():
            pt = self._match(window, lang, ["<lang>", "interface", "pages", fname], ltrb)
            if pt is not None:
                return {"key": key, "pt": pt}
        return None

    def try_close(self, window: Dict, lang: str, page_key: str) -> bool:
        btn_name = CLOSE_BUTTONS["dashboard"] if page_key == "dashboard_page" else CLOSE_BUTTONS["default"]
        zone_decl = ZONES.get("fullscreen")
        ltrb = compute_zone_ltrb(window, zone_decl)

        btn_pt = self._match(window, lang, ["<lang>", "interface", "buttons", btn_name], ltrb)
        if btn_pt is None:
            self._log(f"[ui_guard] close button not found for {page_key}")
            return False

        self._report(f"[UI_GUARD] click close @ {btn_pt[0]},{btn_pt[1]}")
        self._click(btn_pt[0], btn_pt[1])

        # ждём исчезновения страницы
        deadline = time.time() + self.confirm_timeout_s
        while time.time() < deadline:
            if self.scan_open_page(window, lang) is None:
                return True
            time.sleep(0.05)
        return False

    # --- internals ---
    def _match(self, window: Dict, lang: str, parts, ltrb: Zone) -> Optional[Point]:
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
            try: print(msg)
            except Exception: pass

# фабрика (по аналогии с respawn)
def create_engine(**kw):
    return UIGuardEngine(**kw)
