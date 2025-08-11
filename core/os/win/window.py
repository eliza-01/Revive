# core/os/win/window.py
from __future__ import annotations
from typing import Tuple, Optional, Dict

import win32gui
import win32con
import win32api

def _hwnd_from_point(x: int, y: int) -> Optional[int]:
    try:
        hwnd = win32gui.WindowFromPoint((int(x), int(y)))
        if not hwnd:
            return None
        # поднимаем до top-level
        hwnd = win32gui.GetAncestor(hwnd, win32con.GA_ROOT)
        return hwnd
    except Exception:
        return None

def focus_client_area(window_info: Dict) -> None:
    """
    Переводит фокус на окно по точке в центре client-area.
    """
    try:
        cx = int(window_info["x"] + window_info["width"] // 2)
        cy = int(window_info["y"] + window_info["height"] // 2)
        hwnd = _hwnd_from_point(cx, cy)
        if hwnd:
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            win32gui.SetForegroundWindow(hwnd)
    except Exception:
        pass
