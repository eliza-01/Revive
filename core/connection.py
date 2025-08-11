# core/connection.py
from __future__ import annotations
from typing import Optional

from core.arduino.safe_serial import SafeSerial
from core.arduino.send_command import send_command
from core.os.win.window import focus_client_area
from core.os.win.mouse import move_abs, click_left_sys

class ReviveController:
    def __init__(self):
        self._ss = SafeSerial()

    # ---- serial state ----
    def is_connected(self) -> bool:
        return self._ss.is_open()

    def close(self):
        self._ss.close()

    def read(self) -> Optional[str]:
        return self._ss.read_line(timeout_s=1.0)

    # ---- focus/mouse helpers ----
    def focus(self, window_info: dict) -> None:
        focus_client_area(window_info)

    def move(self, x: int, y: int, duration: float = 0.0) -> None:
        move_abs(int(x), int(y), duration=duration)

    def click_left(self) -> None:
        if self.is_connected():
            # прямой вызов send_command для совместимости со старой прошивкой
            try:
                send_command(self._ss.ser, "l")
                return
            except Exception:
                pass
        click_left_sys()

    def click_screen(self, x: int, y: int, window_info: Optional[dict] = None) -> None:
        if window_info:
            self.focus(window_info)
        self.move(int(x), int(y))
        self.click_left()

    # ---- unified send ----
    def send(self, cmd: str):
        if not isinstance(cmd, str):
            return
        if cmd.startswith("click:"):
            try:
                xy = cmd.split(":", 1)[1]
                sx, sy = xy.split(",", 1)
                self.click_screen(int(sx), int(sy))
            except Exception as e:
                print(f"[ctrl] click parse error: {e}")
            return

        if not self.is_connected():
            print("[ctrl] serial not open. command ignored:", cmd)
            return

        ok = self._ss.write_line(cmd)
        if not ok:
            print("[ctrl] send failed:", cmd)
