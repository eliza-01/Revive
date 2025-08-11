# core/vision/capture/window_bgr_capture.py
"""
High-level capture helpers over Win32 GDI backend.

Exports:
- capture_window_region_bgr(window, zone_tuple) -> np.ndarray BGR
- capture_window_region_dict(window, zone_dict) -> np.ndarray BGR
- gdi_capture_zone(window_info, zone_dict)  # backward-compat name
"""
from typing import Optional, Tuple, Dict

import numpy as np
from core.vision.win32.gdi_backend import get_screen

def capture_window_region_bgr(window: Dict, zone: Tuple[int, int, int, int]) -> Optional[np.ndarray]:
    """
    window: {"x","y","width","height"} in screen coords (client area origin)
    zone: (left, top, right, bottom) in client coords
    """
    l, t, r, b = map(int, zone)
    x1 = int(window["x"] + l)
    y1 = int(window["y"] + t)
    x2 = int(window["x"] + r)
    y2 = int(window["y"] + b)
    return get_screen(x1, y1, x2, y2)

def capture_window_region_dict(window: Dict, zone: Dict) -> Optional[np.ndarray]:
    """
    zone:
      - {"fullscreen": True}
      - {"centered": True, "width": W, "height": H}
      - {"left": L, "top": T, "width": W, "height": H}
    """
    wx, wy, ww, wh = window["x"], window["y"], window["width"], window["height"]

    if zone.get("fullscreen"):
        x1, y1 = wx, wy
        x2, y2 = wx + ww, wy + wh
    elif zone.get("centered"):
        w, h = int(zone["width"]), int(zone["height"])
        cx, cy = wx + ww // 2, wy + wh // 2
        x1, y1 = cx - w // 2, cy - h // 2
        x2, y2 = x1 + w, y1 + h
    else:
        x1 = wx + int(zone["left"])
        y1 = wy + int(zone["top"])
        x2 = x1 + int(zone["width"])
        y2 = y1 + int(zone["height"])

    return get_screen(x1, y1, x2, y2)

# backward compatibility alias
def gdi_capture_zone(window_info: Dict, zone: Dict) -> Optional[np.ndarray]:
    return capture_window_region_dict(window_info, zone)
