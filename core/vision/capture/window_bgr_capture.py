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
from core.vision.zones import compute_zone_ltrb

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
    l, t, r, b = compute_zone_ltrb(window, zone)
    return capture_window_region_bgr(window, (l, t, r, b))

# backward compatibility alias
def gdi_capture_zone(window_info: Dict, zone: Dict) -> Optional[np.ndarray]:
    return capture_window_region_dict(window_info, zone)
