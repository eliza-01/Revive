# core/vision/matching/template_matcher.py
# Поиск шаблонов по зонам через серверный resolver (общий, без привязки к engine).
from __future__ import annotations
import importlib
from typing import Optional, Tuple, Dict, Sequence

import cv2
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

def _resolve_path(server: str, lang: str, parts: Sequence[str], engine: str) -> Optional[str]:
    import importlib
    try:
        mod = importlib.import_module(f"core.engines.{engine}.server.{server}.templates.resolver")
        resolve = getattr(mod, "resolve", None)
        if callable(resolve):
            return resolve(lang, *parts)
    except Exception:
        return None
    return None

def match_in_zone(
        window: Dict,
        zone_ltrb: ZoneLTRB,
        server: str,
        lang: str,
        template_parts: Sequence[str],
        threshold: float = 0.87,
        engine: str = None,
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

    # путь к шаблону — только через серверный resolver
    if not engine:
        return None  # явное требование: без имени движка не резолвим
    tpath = _resolve_path(server, lang, template_parts, engine=engine)
    if not tpath:
        return None

    templ = _load_template_abs(tpath)
    if templ is None:
        return None

    # match
    if zone_img.shape[0] < templ.shape[0] or zone_img.shape[1] < templ.shape[1]:
        return None

    res = cv2.matchTemplate(zone_img, templ, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(res)
    if max_val < float(threshold):
        return None

    # центр результата в client-координатах
    tlx, tly = max_loc
    h, w = templ.shape[:2]
    cx_client = int(zone_ltrb[0] + tlx + w / 2)
    cy_client = int(zone_ltrb[1] + tly + h / 2)

    # перевод в экранные координаты
    return (window["x"] + cx_client, window["y"] + cy_client)
