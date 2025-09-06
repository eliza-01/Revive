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
      - {"centered": True, "width": W, "height": H}
      - {"left": L, "top": T, "width": W, "height": H}
    """
    ww, wh = int(window.get("width", 0)), int(window.get("height", 0))

    if isinstance(decl, tuple) and len(decl) == 4:
        l, t, r, b = map(int, decl)
        return (l, t, r, b)

    if isinstance(decl, dict):
        if decl.get("fullscreen"):
            return (0, 0, ww, wh)
        if decl.get("centered"):
            w, h = int(decl["width"]), int(decl["height"])
            l = ww // 2 - w // 2
            t = wh // 2 - h // 2
            return (l, t, l + w, t + h)
        l = int(decl.get("left", 0))
        t = int(decl.get("top, 0")) if "top, 0" in decl else int(decl.get("top", 0))  # защита от опечатки
        w = int(decl.get("width", 0))
        h = int(decl.get("height", 0))
        return (l, t, l + w, t + h)

    # Fallback: весь клиент
    return (0, 0, ww, wh)
