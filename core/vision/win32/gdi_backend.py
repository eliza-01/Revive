# core/vision/win32/gdi_backend.py
"""
Win32 GDI backend: low-level screen and window helpers.

Exports:
- ensure_dpi_awareness()
- get_screen(x1, y1, x2, y2) -> np.ndarray BGR
- get_client_rect(hwnd) -> (abs_x, abs_y, width, height)
- get_window_rect(hwnd) -> (abs_x, abs_y, width, height)
- get_window_info(hwnd, client=True) -> {"x","y","width","height"}
- client_to_screen(hwnd, x, y) -> (ax, ay)
- find_window(title_part="Lineage") -> hwnd | None
- get_client_offset(hwnd) -> ((ax,ay), (l,t,r,b))
"""
from __future__ import annotations

import ctypes
from typing import Optional, Tuple

import numpy as np
import win32con
import win32gui
import win32ui
from core.logging import console

__all__ = [
    "ensure_dpi_awareness",
    "get_screen",
    "get_client_rect",
    "get_window_rect",
    "get_window_info",
    "client_to_screen",
    "find_window",
    "get_client_offset",
]

_dpi_ready = False

def ensure_dpi_awareness() -> None:
    global _dpi_ready
    if _dpi_ready:
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # Per-Monitor v2
        console.log("[GDI] DPI-awareness: Per-Monitor v2")
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()  # System DPI
            console.log("[GDI] DPI-awareness: System")
        except Exception:
            console.log("[GDI] DPI-awareness: failed")
    _dpi_ready = True

def _release_gdi(hwnd, hwnd_dc, srcdc, memdc, bmp) -> None:
    try:
        if bmp:
            win32gui.DeleteObject(bmp.GetHandle())
    except Exception:
        pass
    try:
        if memdc:
            memdc.DeleteDC()
    except Exception:
        pass
    try:
        if srcdc:
            srcdc.DeleteDC()
    except Exception:
        pass
    try:
        if hwnd_dc and hwnd:
            win32gui.ReleaseDC(hwnd, hwnd_dc)
    except Exception:
        pass

def get_screen(x1: int, y1: int, x2: int, y2: int) -> np.ndarray:
    ensure_dpi_awareness()
    w = max(0, int(x2) - int(x1))
    h = max(0, int(y2) - int(y1))
    if w == 0 or h == 0:
        return np.zeros((0, 0, 3), dtype=np.uint8)

    hwnd = win32gui.GetDesktopWindow()
    hwnd_dc = srcdc = memdc = bmp = None
    try:
        hwnd_dc = win32gui.GetWindowDC(hwnd)
        srcdc = win32ui.CreateDCFromHandle(hwnd_dc)
        memdc = srcdc.CreateCompatibleDC()
        bmp = win32ui.CreateBitmap()
        bmp.CreateCompatibleBitmap(srcdc, w, h)
        memdc.SelectObject(bmp)
        memdc.BitBlt((0, 0), (w, h), srcdc, (int(x1), int(y1)), win32con.SRCCOPY)

        bmpinfo = bmp.GetInfo()
        bmpstr = bmp.GetBitmapBits(True)
        bpp = bmpinfo.get("bmBitsPixel", 32)
        channels = max(1, bpp // 8)
        stride = ((bpp * w + 31) // 32) * 4

        buf = np.frombuffer(bmpstr, dtype=np.uint8)
        buf = buf.reshape((h, stride))[:, : w * channels]
        if channels >= 3:
            img = buf.reshape((h, w, channels))[:, :, :3]
        elif channels == 1:
            img = np.repeat(buf.reshape(h, w, 1), 3, axis=2)
        else:
            img = np.zeros((h, w, 3), dtype=np.uint8)
        return img.copy()
    finally:
        _release_gdi(hwnd, hwnd_dc, srcdc, memdc, bmp)

def get_client_rect(hwnd: int) -> tuple[int, int, int, int]:
    l, t, r, b = win32gui.GetClientRect(hwnd)
    ax, ay = win32gui.ClientToScreen(hwnd, (0, 0))
    return ax, ay, r - l, b - t

def get_window_rect(hwnd: int) -> tuple[int, int, int, int]:
    l, t, r, b = win32gui.GetWindowRect(hwnd)
    return l, t, r - l, b - t

def get_window_info(hwnd: int, client: bool = True) -> dict:
    x, y, w, h = get_client_rect(hwnd) if client else get_window_rect(hwnd)
    return {"x": x, "y": y, "width": w, "height": h}

def client_to_screen(hwnd: int, x: int, y: int) -> Tuple[int, int]:
    ax, ay = win32gui.ClientToScreen(hwnd, (int(x), int(y)))
    return ax, ay

def find_window(title_part: str = "Lineage") -> Optional[int]:
    matches: list[int] = []
    def cb(h, _):
        if win32gui.IsWindowVisible(h):
            title = win32gui.GetWindowText(h)
            if title_part.lower() in title.lower():
                matches.append(h)
    win32gui.EnumWindows(cb, None)
    return matches[0] if matches else None

def get_client_offset(hwnd: int) -> Tuple[Tuple[int, int], Tuple[int, int, int, int]]:
    rect = win32gui.GetClientRect(hwnd)
    origin = win32gui.ClientToScreen(hwnd, (0, 0))
    return origin, rect
