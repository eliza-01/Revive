# core/vision/matching/template_matcher.py
# Поиск шаблонов по зонам с учётом серверного resolver'а.
from __future__ import annotations
import importlib
from typing import Optional, Tuple, Dict, Sequence

import cv2, os
import numpy as np
from core.vision.capture.window_bgr_capture import capture_window_region_bgr

Point = Tuple[int, int]
ZoneLTRB = Tuple[int, int, int, int]

def _load_template_abs(path: str) -> Optional[np.ndarray]:
    try:
        img = cv2.imread(path, cv2.IMREAD_COLOR)
        return img if img is not None and img.size else None
    except Exception:
        return None

def _resolve_path(server: str, lang: str, parts: Sequence[str]) -> Optional[str]:
    mod = importlib.import_module(f"core.servers.{server}.templates.resolver")
    return getattr(mod, "resolve")(lang, *parts)

def match_in_zone(
        window: Dict,
        zone_ltrb: ZoneLTRB,
        server: str,
        lang: str,
        template_parts: Sequence[str],
        threshold: float = 0.87,
) -> Optional[Point]:
    """
    Вернёт центр найденного шаблона в ЭКРАННЫХ координатах или None.
    zone_ltrb: (left, top, right, bottom) — client coords.
    """
    if not window:
        return None

    # захват зоны
    zone_img = capture_window_region_bgr(window, zone_ltrb)
    if zone_img is None or zone_img.size == 0:
        return None

    # загрузка шаблона
    tpath = _resolve_path(server, lang, template_parts)
     # Fallback: templates из engines/autofarm
    if not tpath:
        try:
            ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))  # -> core
            af1 = os.path.join(ROOT, "engines", "autofarm", server, "templates", lang, *template_parts)
            af2 = os.path.join(ROOT, "engines", "autofarm", "common", "templates", lang, *template_parts)
            if os.path.exists(af1):
                tpath = af1
            elif os.path.exists(af2):
                tpath = af2
        except Exception:
            tpath = None
    if not tpath:
        return None
    templ = _load_template_abs(tpath)
    if templ is None:
        return None

    # match
    if zone_img.shape[0] < templ.shape[0] or zone_img.shape[1] < templ.shape[1]:
        return None

    res = cv2.matchTemplate(zone_img, templ, cv2.TM_CCOEFF_NORMED)
    min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)
    if max_val < float(threshold):
        return None

    # центр результата в client-координатах
    tlx, tly = max_loc
    h, w = templ.shape[:2]
    cx_client = int(zone_ltrb[0] + tlx + w / 2)
    cy_client = int(zone_ltrb[1] + tly + h / 2)

    # перевод в экранные координаты
    cx_screen = window["x"] + cx_client
    cy_screen = window["y"] + cy_client
    return (cx_screen, cy_screen)
