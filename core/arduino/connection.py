# core/arduino/connection.py
from __future__ import annotations
from typing import Optional

from core.arduino.safe_serial import SafeSerial
from core.os.win.window import focus_client_area
from core.os.win.mouse import move_abs


class ReviveController:
    """
    Универсальный контроллер под движки.
    КОНТРАКТ:
        .send("click:x,y")  -> сфокусироваться (если заранее передали окно), переместить курсор и сделать клик ЧЕРЕЗ ARDUINO
    Только Arduino-клик. Если Serial недоступен — клик НЕ производится (никаких системных fallback-ов).

    Поток использования:
        1) controller.focus(window_info)  # по желанию, если надо сфокусировать окно
        2) controller.send("click:123,456")
    """

    def __init__(self):
        self._ss = SafeSerial()

    # ---- serial state ----
    def is_connected(self) -> bool:
        return self._ss.is_open()

    def close(self):
        self._ss.close()

    def read(self) -> Optional[str]:
        return self._ss.read_line(timeout_s=1.0)

    # ---- focus/mouse helpers (движки могут вызывать отдельно) ----
    def focus(self, window_info: dict) -> None:
        """Фокусируем клиентскую область окна (без клика)."""
        try:
            focus_client_area(window_info)
        except Exception as e:
            print(f"[ctrl] focus fail: {e}")

    def move(self, x: int, y: int, duration: float = 0.0) -> None:
        """Перемещаем курсор на абсолютные координаты экрана."""
        try:
            move_abs(int(x), int(y), duration=duration)
        except Exception as e:
            print(f"[ctrl] move fail: {e}")

    # ---- arduino-only click ----
    def _click_left_arduino(self) -> bool:
        """
        Единственный допустимый способ клика: через Arduino.
        Возвращает True/False по факту отправки команды.
        """
        ok = self._ss.write_line("l")  # SafeSerial сам добавит '\n' и переподключится при необходимости
        if not ok:
            print("[ctrl] arduino click failed (serial not open or write error)")
        return ok

    # ---- high-level helpers ----
    def click_screen(self, x: int, y: int, window_info: Optional[dict] = None) -> bool:
        """
        (Опционально) фокусируем окно, двигаем курсор и кликаем ЧЕРЕЗ Arduino.
        """
        if window_info:
            self.focus(window_info)
        self.move(int(x), int(y))
        return self._click_left_arduino()

    # ---- unified send API (контракт для движков) ----
    def send(self, cmd: str):
        """
        Поддерживаем минимум команд:
          - "click:x,y"  → переместить курсор и кликнуть через Arduino.
          - любые другие строки → отправляются как есть в Arduino (через SafeSerial.write_line).
        """
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

        # произвольная команда в Arduino (например, на будущее)
        if not self.is_connected():
            print("[ctrl] serial not open. command ignored:", cmd)
            return
        ok = self._ss.write_line(cmd)
        if not ok:
            print("[ctrl] send failed:", cmd)
