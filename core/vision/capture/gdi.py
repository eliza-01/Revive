# core/vision/capture/gdi.py
"""
Compatibility shim for legacy imports.

Provides:
- find_window(title)
- get_window_info(hwnd, client=True)
- get_window_rect/get_client_rect
- client_to_screen
- gdi_capture_zone(window_info, zone_dict)
"""
from typing import Optional, Tuple, Dict

from core.vision.win32.gdi_backend import (
    find_window,
    get_window_info,
    get_window_rect,
    get_client_rect,
    client_to_screen,
)
from core.vision.capture.window_bgr_capture import gdi_capture_zone
