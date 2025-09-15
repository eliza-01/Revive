# core/vision/zones.py
from __future__ import annotations
from typing import Tuple, Dict, Union

ZoneLTRB = Tuple[int, int, int, int]
ZoneDecl = Union[ZoneLTRB, dict]

def compute_zone_ltrb(window: Dict, decl: ZoneDecl) -> ZoneLTRB:
    """
    Универсальное приведение декларации зоны к (left, top, right, bottom)
    в КЛИЕНТСКИХ координатах окна.

    Поддерживаем:
      - (l, t, r, b)
      - {"fullscreen": True}
      - {"centered": True, "width": W, "height": H}                 # центр по X и Y
      - {"centered_x": True, "width": W, "height": H, "top": T}      # центр по X, явный top
      - {"centered_y": True, "height": H, "left": L, "width": W}     # центр по Y, явный left
      - {"left": L, "top": T, "width": W, "height": H}
    """
    ww, wh = int(window.get("width", 0)), int(window.get("height", 0))

    # tuple (l, t, r, b)
    if isinstance(decl, tuple) and len(decl) == 4:
        l, t, r, b = map(int, decl)
        return (l, t, r, b)

    if isinstance(decl, dict):
        # fullscreen
        if decl.get("fullscreen"):
            return (0, 0, ww, wh)

        # новый вариант: центрировать по одной оси
        if decl.get("centered_x") or decl.get("centered_y"):
            w = int(decl.get("width", 0))
            h = int(decl.get("height", 0))
            # защита от опечатки top, 0
            t = int(decl.get("top, 0")) if "top, 0" in decl else int(decl.get("top", 0))
            l = int(decl.get("left", 0))

            if decl.get("centered_x"):
                l = max(0, ww // 2 - w // 2)
            if decl.get("centered_y"):
                t = max(0, wh // 2 - h // 2)

            return (l, t, l + w, t + h)

        # старый вариант: центр сразу по X и Y
        if decl.get("centered"):
            w, h = int(decl["width"]), int(decl["height"])
            l = ww // 2 - w // 2
            t = wh // 2 - h // 2
            return (l, t, l + w, t + h)

        # явные координаты
        l = int(decl.get("left", 0))
        t = int(decl.get("top, 0")) if "top, 0" in decl else int(decl.get("top", 0))  # защита от опечатки
        w = int(decl.get("width", 0))
        h = int(decl.get("height", 0))
        return (l, t, l + w, t + h)

    # Fallback: весь клиент
    return (0, 0, ww, wh)
