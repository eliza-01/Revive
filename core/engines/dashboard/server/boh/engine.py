# core/engines/dashboard/server/boh/engine.py
from __future__ import annotations
import time
from typing import Any, Dict, Optional, Tuple

import cv2
import numpy as np

from core.logging import console
from core.vision.capture.window_bgr_capture import capture_window_region_bgr
from .dashboard_data import ZONES, TEMPLATES
from .templates.resolver import resolve as tpl_resolve

ZoneLTRB = Tuple[int, int, int, int]

def _zone_ltrb(win: Dict[str, Any], decl) -> ZoneLTRB:
    if isinstance(decl, tuple) and len(decl) == 4:
        return tuple(map(int, decl))
    if isinstance(decl, dict):
        ww = int(win.get("width", 0)); wh = int(win.get("height", 0))
        if decl.get("fullscreen"):
            return (0, 0, ww, wh)
        if decl.get("centered"):
            w = int(decl.get("width", 0)); h = int(decl.get("height", 0))
            l = ww // 2 - w // 2; t = wh // 2 - h // 2
            return (l, t, l + w, t + h)
        l = int(decl.get("left", 0)); t = int(decl.get("top", 0))
        r = l + int(decl.get("width", ww)); b = t + int(decl.get("height", wh))
        return (l, t, r, b)
    return (0, 0, int(win.get("width", 0)), int(win.get("height", 0)))

def _match_on_window(win: Dict[str, Any], lang: str, tpl_key: str,
                     zone_key: str = "fullscreen", threshold: float = 0.87) -> Optional[Tuple[int,int,int,int]]:
    parts = TEMPLATES.get(tpl_key)
    if not parts:
        return None
    path = tpl_resolve(lang, *parts)
    if not path:
        return None

    l, t, r, b = _zone_ltrb(win, ZONES.get(zone_key, ZONES["fullscreen"]))
    img = capture_window_region_bgr(win, (l, t, r, b))
    if img is None or img.size == 0:
        return None

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    tpl  = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
    if tpl is None or tpl.size == 0:
        return None

    th, tw = tpl.shape[:2]
    res = cv2.matchTemplate(gray, tpl, cv2.TM_CCOEFF_NORMED)
    _minVal, maxVal, _minLoc, maxLoc = cv2.minMaxLoc(res)
    if float(maxVal) < float(threshold):
        return None
    x = l + int(maxLoc[0]); y = t + int(maxLoc[1])
    return (x, y, tw, th)

def _visible(win: Dict[str, Any], lang: str, tpl_key: str, zone_key: str = "fullscreen", thr: float = 0.87) -> bool:
    return _match_on_window(win, lang, tpl_key, zone_key, thr) is not None

def _click_center(controller, rect: Tuple[int,int,int,int]) -> None:
    (x, y, w, h) = rect
    cx, cy = x + w // 2, y + h // 2
    try:
        controller.send(f"click:{int(cx)},{int(cy)}")
    except Exception:
        pass

class DashboardEngine:
    """
    Общий движок Dashboard:
      - открывает/закрывает Alt+B;
      - ждёт готовности (не заблокирован);
      - направляет в разделы (buffer/teleport/...).
    """
    def __init__(self, state: Dict[str, Any], server: str, controller: Any,
                 get_window, get_language):
        self.s = state
        self.server = (server or "boh").lower()
        self.controller = controller
        self.get_window = get_window
        self.get_language = get_language

    # ---------- utils ----------
    def _hud(self, status: str, text: str):
        try:
            console.hud(status, text)
        except Exception:
            console.log(f"[HUD/{status}] {text}")

    def _lang(self) -> str:
        try:
            return (self.get_language() or "rus").lower()
        except Exception:
            return "rus"

    def _win(self) -> Optional[Dict[str, Any]]:
        try:
            return self.get_window() or None
        except Exception:
            return None

    def _send_alt_b(self):
        try:
            self.controller.send("altB")
        except Exception:
            pass

    # ---------- dashboard state ----------
    def is_open(self, thr: float = 0.87) -> bool:
        win = self._win()
        if not win:
            return False
        return _visible(win, self._lang(), "dashboard_init", "fullscreen", thr)

    def close_if_open(self, timeout_s: float = 1.5) -> None:
        if not self.is_open():
            return
        self._send_alt_b()
        t0 = time.time()
        while time.time() - t0 < timeout_s:
            if not self.is_open():
                return
            time.sleep(0.05)

    def open(self, timeout_s: float = 3.0) -> bool:
        """Просто открыть Alt+B и дождаться появления."""
        win = self._win()
        if not win:
            self._hud("err", "[dashboard] окно игры не найдено")
            return False
        self._send_alt_b()
        t0 = time.time()
        while time.time() - t0 < timeout_s:
            if self.is_open():
                self._hud("ok", "[dashboard] Alt+B открыт")
                return True
            time.sleep(0.05)
        self._hud("err", "[dashboard] не удалось открыть (Alt+B)")
        return False

    def open_fresh(self, timeout_s: float = 3.0) -> bool:
        """Закрыть, если открыт → открыть заново."""
        self.close_if_open(timeout_s=1.2)
        return self.open(timeout_s=timeout_s)

    # ---------- lock handling ----------
    def _locked_any(self, thr: float = 0.87) -> bool:
        win = self._win()
        if not win:
            return False
        lang = self._lang()
        return (
            _visible(win, lang, "dashboard_is_locked_1", "fullscreen", thr) or
            _visible(win, lang, "dashboard_is_locked_2", "fullscreen", thr)
        )

    def wait_ready(self, timeout_s: float = 12.0, probe_interval_s: float = 1.0) -> bool:
        """
        Пока виден любой 'dashboard_is_locked_*' — жмём 'l' периодически.
        """
        t0 = time.time()
        next_probe = 0.0
        while time.time() - t0 < timeout_s:
            if not self._locked_any():
                return True
            now = time.time()
            if now >= next_probe:
                try:
                    self.controller.send("l")
                except Exception:
                    pass
                next_probe = now + max(0.2, float(probe_interval_s))
            time.sleep(0.05)
        console.log("[dashboard] всё ещё заблокирован")
        return False

    def ensure_open_and_ready(self) -> bool:
        if not self.is_open():
            if not self.open_fresh(timeout_s=3.0):
                return False
        # даже если уже был открыт — проверим «разблокировку»
        return self.wait_ready(timeout_s=12.0, probe_interval_s=1.0)

    # ---------- navigation ----------
    def goto(self, section: str, timeout_s: float = 3.0, thr: float = 0.87) -> bool:
        """
        Переход в раздел Dashboard:
          - "buffer": click 'dashboard_buffer_button' → wait 'dashboard_buffer_init'
          - "teleport": click 'dashboard_teleport_button' → wait 'dashboard_teleport'
        """
        section = (section or "").lower().strip()
        if section not in ("buffer", "teleport"):
            self._hud("err", f"[dashboard] неизвестный раздел: {section}")
            return False

        win = self._win()
        if not win:
            self._hud("err", "[dashboard] окно игры не найдено")
            return False

        lang = self._lang()
        btn_key = "dashboard_buffer_button" if section == "buffer" else "dashboard_teleport_button"
        init_key = "dashboard_buffer_init" if section == "buffer" else "dashboard_teleport"

        rect = _match_on_window(win, lang, btn_key, "fullscreen", thr)
        if not rect:
            self._hud("err", f"[dashboard] кнопка раздела '{section}' не найдена")
            return False

        _click_center(self.controller, rect)

        t0 = time.time()
        while time.time() - t0 < timeout_s:
            if _visible(win, lang, init_key, "fullscreen", thr):
                self._hud("ok", f"[dashboard] раздел '{section}' открыт")
                return True
            time.sleep(0.05)

        self._hud("err", f"[dashboard] раздел '{section}' не открылся")
        return False
