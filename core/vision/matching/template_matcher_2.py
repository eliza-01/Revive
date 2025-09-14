# core/vision/matching/template_matcher_2.py
# Универсальный мульти-матчер по зоне: несколько ключей, мультимасштаб, с резолвером
# core.engines.<engine>.server.<server>.templates.resolver

from __future__ import annotations
from typing import Optional, Tuple, Dict, Sequence, List

import cv2
import numpy as np

from core.vision.capture.window_bgr_capture import capture_window_region_bgr
from core.logging import console

Point = Tuple[int, int]
ZoneLTRB = Tuple[int, int, int, int]


def _load_template_abs(path: str) -> Optional[np.ndarray]:
    try:
        img = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
        return img if img is not None and img.size else None
    except Exception:
        return None


def _resolve_path(server: str, lang: str, parts: Sequence[str], engine: str) -> Optional[str]:
    """
    Ожидаем server-специфичный резолвер по пути:
      core.engines.<engine>.server.<server>.templates.resolver
    parts обычно вида ["<lang>", "reborn_banner.png"].
    """
    try:
        mod_name = f"core.engines.{engine}.server.{server}.templates.resolver"
        mod = __import__(mod_name, fromlist=["resolve"])
        resolve = getattr(mod, "resolve", None)
        if callable(resolve):
            return resolve(lang, *parts)
    except Exception:
        return None
    return None


def match_key_in_zone_single(
    *,
    window: Dict,
    zone_ltrb: ZoneLTRB,
    server: str,
    lang: str,
    template_parts: Sequence[str],
    threshold: float = 0.85,
    engine: str = "respawn",
) -> Optional[Point]:
    """
    Матч ОДНОГО шаблона в зоне.
    Возвращает центр совпадения в ЭКРАННЫХ координатах или None.
    """
    if not window:
        return None

    zone_img_bgr = capture_window_region_bgr(window, zone_ltrb)
    if zone_img_bgr is None or zone_img_bgr.size == 0:
        return None

    # Приводим зону к GRAY, чтобы тип совпадал с шаблоном
    if zone_img_bgr.ndim == 3:
        zone_gray = cv2.cvtColor(zone_img_bgr, cv2.COLOR_BGR2GRAY)
    else:
        zone_gray = zone_img_bgr

    teleportath = _resolve_path(server, (lang or "rus").lower(), template_parts, engine=engine)
    if not teleportath:
        return None

    templ = _load_template_abs(teleportath)
    if templ is None:
        return None

    if zone_gray.shape[0] < templ.shape[0] or zone_gray.shape[1] < templ.shape[1]:
        return None

    res = cv2.matchTemplate(zone_gray, templ, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(res)
    if float(max_val) < float(threshold):
        return None

    tlx, tly = max_loc
    h, w = templ.shape[:2]
    cx_client = int(zone_ltrb[0] + tlx + w / 2)
    cy_client = int(zone_ltrb[1] + tly + h / 2)
    return (int(window["x"] + cx_client), int(window["y"] + cy_client))


def match_multi_in_zone(
    *,
    window: Dict,
    zone_ltrb: ZoneLTRB,
    server: str,
    lang: str,
    templates_map: Dict[str, Sequence[str]],
    key_order: Optional[List[str]] = None,
    threshold: float = 0.85,
    engine: str = "respawn",
    scales: Sequence[float] = (1.0, 0.9, 1.1, 0.8, 1.2),
    debug: bool = False,
) -> Optional[Tuple[Point, str]]:
    """
    Мульти-матчер: обходит ключи в заданном порядке (key_order) и ищет каждый шаблон
    с несколькими масштабами. Возвращает ((x,y), key) либо None.

    templates_map: { "reborn_banner": ["<lang>", "reborn_banner.png"], ... }
    key_order:     приоритет проверки; если None — используем templates_map.keys()
    threshold:     порог TM_CCOEFF_NORMED
    """
    if not window:
        return None

    # Захват зоны
    zone_img = capture_window_region_bgr(window, zone_ltrb)
    if zone_img is None or zone_img.size == 0:
        return None

    gray = cv2.cvtColor(zone_img, cv2.COLOR_BGR2GRAY)

    # Порядок ключей
    keys = list(key_order) if key_order else list(templates_map.keys())
    if not keys:
        return None

    best = None  # {'score': float, 'loc': (x,y), 'w': int, 'h': int, 'key': str}

    # Проход по ключам/масштабам
    for key in keys:
        parts = templates_map.get(key)
        if not parts:
            continue
        teleportath = _resolve_path(server, (lang or "rus").lower(), parts, engine=engine)
        if not teleportath:
            if debug:
                console.log(f"[tm2] no template path for key={key} (server={server}, engine={engine})")
            continue

        teleportl = _load_template_abs(teleportath)
        if teleportl is None or teleportl.size == 0:
            if debug:
                console.log(f"[tm2] failed to read template: {teleportath}")
            continue

        for s in scales:
            tw = max(1, int(round(teleportl.shape[1] * s)))
            th = max(1, int(round(teleportl.shape[0] * s)))
            t = cv2.resize(
                teleportl,
                (tw, th),
                interpolation=cv2.INTER_AREA if s < 1.0 else cv2.INTER_CUBIC
            )
            if t.shape[0] > gray.shape[0] or t.shape[1] > gray.shape[1]:
                continue

            res = cv2.matchTemplate(gray, t, cv2.TM_CCOEFF_NORMED)
            _, maxVal, _, maxLoc = cv2.minMaxLoc(res)
            score = float(maxVal)
            if best is None or score > best["score"]:
                best = {"score": score, "loc": maxLoc, "w": t.shape[1], "h": t.shape[0], "key": key}

    # Проверка порога и перевод координат в ЭКРАННЫЕ
    if best and best["score"] >= float(threshold):
        zl, zt, _, _ = zone_ltrb
        cx_client = zl + best["loc"][0] + best["w"] // 2
        cy_client = zt + best["loc"][1] + best["h"] // 2
        cx_screen = int(window.get("x", 0)) + int(cx_client)
        cy_screen = int(window.get("y", 0)) + int(cy_client)

        if debug:
            console.log(f"[tm2] {best['key']} score={best['score']:.3f} @ ({cx_screen},{cy_screen})")

        return ((cx_screen, cy_screen), best["key"])

    return None