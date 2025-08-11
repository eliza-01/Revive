# core/os/win/mouse.py
from __future__ import annotations
import time
from typing import Tuple

import win32api
import win32con

def move_abs(x: int, y: int, duration: float = 0.0) -> None:
    """
    Перемещение курсора в абсолютные экранные координаты.
    duration>0 → линейная анимация.
    """
    if duration <= 0:
        win32api.SetCursorPos((int(x), int(y)))
        return

    sx, sy = win32api.GetCursorPos()
    dx = int(x) - sx
    dy = int(y) - sy
    steps = max(1, int(duration / 0.01))
    for i in range(1, steps + 1):
        nx = sx + int(dx * i / steps)
        ny = sy + int(dy * i / steps)
        win32api.SetCursorPos((nx, ny))
        time.sleep(0.01)

def click_left_sys() -> None:
    x, y = win32api.GetCursorPos()
    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, x, y, 0, 0)
    time.sleep(0.01)
    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, x, y, 0, 0)
