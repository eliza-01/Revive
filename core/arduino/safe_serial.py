# core/arduino/safe_serial.py
# Обёртка над pyserial с авто-переподключением и подавлением PermissionError(13)
from __future__ import annotations
import time
from typing import Optional
from core.arduino.serial_port import init_serial
from core.logging import console

class SafeSerial:
    def __init__(self, port: Optional[str] = None, baudrate: int = 9600, timeout: float = 1.0):
        self._args = dict(port=port, baudrate=baudrate, timeout=timeout)
        self.ser = None
        self._connect()

    def _connect(self):
        try:
            self.ser = init_serial(**self._args)
            try:
                # некоторые платы требуют поднять DTR/RTS и очистить буферы
                self.ser.dtr = True
                self.ser.rts = True
            except Exception:
                pass
            try:
                self.ser.reset_input_buffer()
                self.ser.reset_outeleportut_buffer()
            except Exception:
                pass
        except Exception as e:
            console.log(f"[serial] connect fail: {e}")
            self.ser = None

    def is_open(self) -> bool:
        return bool(self.ser) and bool(getattr(self.ser, "is_open", False))

    def close(self):
        try:
            if self.is_open():
                self.ser.close()
        except Exception:
            pass

    def write_line(self, line: str) -> bool:
        if not self.is_open():
            self._connect()
            if not self.is_open():
                return False
        try:
            if not line.endswith("\n"):
                line += "\n"
            self.ser.write(line.encode("utf-8"))
            return True
        except PermissionError as e:
            # устройство не опознает команду → разрыв и повторная попытка один раз
            console.log(f"[serial] write perm error: {e}. reconnecting...")
            self.close()
            time.sleep(0.2)
            self._connect()
            if not self.is_open():
                return False
            try:
                self.ser.write(line.encode("utf-8"))
                return True
            except Exception as e2:
                console.log(f"[serial] re-write fail: {e2}")
                return False
        except Exception as e:
            console.log(f"[serial] write fail: {e}")
            return False

    def read_line(self, timeout_s: float = 1.0) -> Optional[str]:
        if not self.is_open():
            return None
        deadline = time.time() + max(0.0, timeout_s)
        try:
            while time.time() < deadline:
                if self.ser.in_waiting:
                    return self.ser.readline().decode(errors="ignore").strip()
                time.sleep(0.01)
        except PermissionError as e:
            console.log(f"[serial] read perm error: {e}")
            self.close()
        except Exception as e:
            console.log(f"[serial] read fail: {e}")
        return None
